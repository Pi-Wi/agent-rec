"""
Corpus importer tests, fully offline.

Each importer (Langfuse / LangSmith / OpenTelemetry GenAI) parses a small
representative export into a synthesized OpenAI-dialect cassette, which the
existing decode/keying machinery then reads exactly like a recorded one.  The
tests pin the contracts that matter: faithful decode, honest provenance
metadata, cross-provider semantic-key grouping (imported and recorded traffic
land in the same group), idempotent re-import, graceful per-record skips, and
an end-to-end migration driven entirely by imported baselines.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agentrec import (
    FileStore,
    build_comparators,
    fingerprint_of,
    import_corpus,
    run_migration,
)
from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.cli import main as cli_main
from agentrec.importers import IMPORT_PREFIX
from agentrec.providers import conversation_of, decode_interaction


def _write(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Langfuse
# ---------------------------------------------------------------------------

LANGFUSE_OBS = {
    "id": "obs-1",
    "type": "GENERATION",
    "model": "gpt-4o-mini",
    "input": [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "Capital of France?"},
    ],
    "output": "Paris",
    "usage": {"promptTokens": 12, "completionTokens": 1},
    "startTime": "2026-01-01T00:00:00Z",
    "metadata": {"category": "geo"},
}


async def test_langfuse_import_synthesizes_decodable_cassette(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    src = _write_jsonl(tmp_path / "langfuse.jsonl", [LANGFUSE_OBS])

    summary = await import_corpus(src, store, source="langfuse")
    assert summary.imported_count == 1 and summary.skipped_count == 0
    (cid,) = summary.imported
    assert cid.startswith(IMPORT_PREFIX)

    interaction = await store.load(cid)
    # Synthesized response decodes to the recorded answer.
    assert decode_interaction(interaction).text == "Paris"
    # Conversation is faithful (system lifted out, user message kept).
    conversation = conversation_of(interaction)
    assert conversation.system == "You are terse."
    assert conversation.messages[-1]["content"] == "Capital of France?"
    # Honest provenance.
    assert interaction.metadata["imported"] is True
    assert interaction.metadata["imported_from"] == "langfuse"
    assert interaction.metadata["model"] == "gpt-4o-mini"
    assert interaction.metadata["category"] == "geo"
    assert interaction.metadata["recorded_at"] == "2026-01-01T00:00:00Z"
    # Token counts survive into the report path.
    from agentrec.providers import usage_of

    usage = usage_of(decode_interaction(interaction))
    assert usage.prompt_total == 12 and usage.output == 1


async def test_langfuse_plain_string_input(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    obs = {"id": "o2", "type": "GENERATION", "model": "gpt-4o-mini",
           "input": "just a string prompt", "output": {"content": "ok"}}
    summary = await import_corpus(_write_jsonl(tmp_path / "lf.jsonl", [obs]), store, source="langfuse")
    (cid,) = summary.imported
    conversation = conversation_of(await store.load(cid))
    assert conversation.messages[0]["content"] == "just a string prompt"
    assert decode_interaction(await store.load(cid)).text == "ok"


# ---------------------------------------------------------------------------
# LangSmith
# ---------------------------------------------------------------------------

LANGSMITH_RUN = {
    "id": "run-1",
    "run_type": "llm",
    "start_time": "2026-01-02T00:00:00Z",
    "inputs": {"messages": [[
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Q?"},
    ]]},
    "outputs": {
        "generations": [[{"text": "A.", "message": {"kwargs": {"content": "A."}}}]],
        "llm_output": {"token_usage": {"prompt_tokens": 10, "completion_tokens": 2}},
    },
    "extra": {"invocation_params": {"model": "gpt-4o"}},
}


async def test_langsmith_import_handles_nested_batch_and_lc_messages(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    summary = await import_corpus(
        _write(tmp_path / "ls.json", [LANGSMITH_RUN]), store, source="langsmith"
    )
    (cid,) = summary.imported
    interaction = await store.load(cid)
    conversation = conversation_of(interaction)
    assert conversation.system == "sys"
    assert conversation.messages[-1]["content"] == "Q?"
    assert decode_interaction(interaction).text == "A."
    assert interaction.metadata["model"] == "gpt-4o"
    from agentrec.providers import usage_of

    assert usage_of(decode_interaction(interaction)).prompt_total == 10


async def test_langsmith_langchain_serialized_messages(tmp_path: Path):
    """LangChain's serialized HumanMessage/AIMessage form is understood."""
    store = FileStore(tmp_path / "corpus")
    run = {
        "id": "run-lc",
        "run_type": "llm",
        "inputs": {"messages": [[
            {"lc": 1, "type": "constructor",
             "id": ["langchain", "schema", "messages", "HumanMessage"],
             "kwargs": {"content": "hi there"}},
        ]]},
        "outputs": {"generations": [[{"message": {"kwargs": {
            "content": "hello", "usage_metadata": {"input_tokens": 4, "output_tokens": 1}}}}]]},
        "extra": {"invocation_params": {"model_name": "gpt-4o-mini"}},
    }
    summary = await import_corpus(_write(tmp_path / "lc.json", [run]), store, source="langsmith")
    (cid,) = summary.imported
    interaction = await store.load(cid)
    assert conversation_of(interaction).messages[0]["content"] == "hi there"
    assert decode_interaction(interaction).text == "hello"
    from agentrec.providers import usage_of

    assert usage_of(decode_interaction(interaction)).output == 1


# ---------------------------------------------------------------------------
# OpenTelemetry GenAI
# ---------------------------------------------------------------------------

OTEL_SPAN_FLAT = {
    "name": "chat gpt-4o-mini",
    "spanId": "span-abc",
    "startTimeUnixNano": "1767225600000000000",
    "attributes": {
        "gen_ai.system": "openai",
        "gen_ai.request.model": "gpt-4o-mini",
        "gen_ai.prompt.0.role": "system",
        "gen_ai.prompt.0.content": "You are helpful.",
        "gen_ai.prompt.1.role": "user",
        "gen_ai.prompt.1.content": "What is 2+2?",
        "gen_ai.completion.0.role": "assistant",
        "gen_ai.completion.0.content": "4",
        "gen_ai.usage.input_tokens": 12,
        "gen_ai.usage.output_tokens": 1,
    },
}


async def test_otel_flat_attribute_span_import(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    summary = await import_corpus(
        _write(tmp_path / "otel.json", [OTEL_SPAN_FLAT]), store, source="otel"
    )
    (cid,) = summary.imported
    interaction = await store.load(cid)
    conversation = conversation_of(interaction)
    assert conversation.system == "You are helpful."
    assert conversation.messages[-1]["content"] == "What is 2+2?"
    assert decode_interaction(interaction).text == "4"
    assert interaction.metadata["imported_from"] == "otel"
    assert interaction.metadata["imported_provider"] == "openai"
    assert interaction.metadata["recorded_at"].startswith("2026-01-01")


async def test_otel_otlp_resource_spans_with_typed_values(tmp_path: Path):
    """OTLP nesting (resourceSpans/scopeSpans/spans) + AnyValue-wrapped attrs."""
    store = FileStore(tmp_path / "corpus")
    otlp = {"resourceSpans": [{"scopeSpans": [{"spans": [{
        "name": "anthropic.messages",
        "spanId": "s1",
        "attributes": [
            {"key": "gen_ai.system", "value": {"stringValue": "anthropic"}},
            {"key": "gen_ai.request.model", "value": {"stringValue": "claude-3-5-sonnet"}},
            {"key": "gen_ai.prompt.0.role", "value": {"stringValue": "user"}},
            {"key": "gen_ai.prompt.0.content", "value": {"stringValue": "ping"}},
            {"key": "gen_ai.completion.0.content", "value": {"stringValue": "pong"}},
            {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "5"}},
            {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "1"}},
        ],
    }]}]}]}
    summary = await import_corpus(_write(tmp_path / "otlp.json", [otlp]), store, source="otel")
    (cid,) = summary.imported
    interaction = await store.load(cid)
    assert conversation_of(interaction).messages[0]["content"] == "ping"
    assert decode_interaction(interaction).text == "pong"
    assert interaction.metadata["model"] == "claude-3-5-sonnet"
    from agentrec.providers import usage_of

    assert usage_of(decode_interaction(interaction)).prompt_total == 5


# ---------------------------------------------------------------------------
# Cross-cutting contracts
# ---------------------------------------------------------------------------


async def test_imported_cassette_groups_with_recorded_anthropic(tmp_path: Path):
    """An imported OpenAI-shaped prompt shares a semantic_key with the same
    prompt recorded natively against Anthropic — they migrate as one row."""
    store = FileStore(tmp_path / "corpus")
    obs = {"id": "g1", "type": "GENERATION", "model": "gpt-4o-mini",
           "input": [{"role": "user", "content": "Hello"}], "output": "Hi"}
    summary = await import_corpus(_write_jsonl(tmp_path / "lf.jsonl", [obs]), store, source="langfuse")
    imported = await store.load(summary.imported[0])

    anthropic = CapturedInteraction(
        request=CapturedRequest(
            method="POST", url="https://api.anthropic.com/v1/messages", headers=[],
            content=json.dumps({"model": "claude-3-5-haiku", "max_tokens": 64,
                                "messages": [{"role": "user", "content": "Hello"}]}).encode(),
        ),
        response_status=200, response_headers=[], response_extensions={}, chunks=[], metadata={},
    )
    assert fingerprint_of(imported).semantic_key == fingerprint_of(anthropic).semantic_key
    # And it matches the key the importer pinned into metadata.
    assert imported.metadata["semantic_key"] == fingerprint_of(anthropic).semantic_key


async def test_reimport_is_idempotent(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    src = _write_jsonl(tmp_path / "lf.jsonl", [LANGFUSE_OBS])
    first = await import_corpus(src, store, source="langfuse")
    second = await import_corpus(src, store, source="langfuse")
    assert first.imported == second.imported  # same deterministic id
    assert len([i for i in store.ids() if i.startswith(IMPORT_PREFIX)]) == 1


async def test_bad_records_are_skipped_not_fatal(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    rows = [
        LANGFUSE_OBS,
        {"id": "empty", "type": "GENERATION", "input": None},  # no usable input
        {"id": "sys-only", "type": "GENERATION", "input": [{"role": "system", "content": "x"}]},
        "not-an-object",
    ]
    summary = await import_corpus(_write_jsonl(tmp_path / "mixed.jsonl", rows), store, source="langfuse")
    assert summary.imported_count == 1
    assert summary.skipped_count == 3
    reasons = {ref: reason for ref, reason in summary.skipped}
    assert any("no usable input" in r for r in reasons.values())
    assert any("only a system" in r for r in reasons.values())


async def test_category_override_tags_untagged_rows(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    summary = await import_corpus(
        _write(tmp_path / "otel.json", [OTEL_SPAN_FLAT]), store, source="otel", category="batch-7"
    )
    interaction = await store.load(summary.imported[0])
    assert interaction.metadata["category"] == "batch-7"


async def test_auto_detection_picks_source(tmp_path: Path):
    store = FileStore(tmp_path / "corpus")
    summary = await import_corpus(
        _write_jsonl(tmp_path / "lf.jsonl", [LANGFUSE_OBS]), store, source="auto"
    )
    assert summary.source == "langfuse" and summary.imported_count == 1


# ---------------------------------------------------------------------------
# end-to-end + CLI
# ---------------------------------------------------------------------------


def _anthropic_target(text: str = "Paris") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "claude-haiku-4-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 8, "output_tokens": 1},
        })
    return httpx.MockTransport(handler)


async def test_imported_corpus_migrates_end_to_end(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = FileStore(tmp_path / "corpus")
    await import_corpus(_write_jsonl(tmp_path / "lf.jsonl", [LANGFUSE_OBS]), store, source="langfuse")

    report = await run_migration(
        store, "claude-haiku-4-5", build_comparators("exact"),
        inner_transport=_anthropic_target("Paris"),
    )
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.status == "ok"
    assert row.baseline_id.startswith(IMPORT_PREFIX)  # imported cassette IS a baseline
    assert row.baseline_model == "gpt-4o-mini"
    assert row.target_text == "Paris"
    assert row.category == "geo"
    assert report.all_passed


def test_cli_import_smoke(tmp_path: Path, capsys):
    src = _write_jsonl(tmp_path / "langfuse.jsonl", [LANGFUSE_OBS])
    corpus = tmp_path / "corpus"
    code = cli_main(["import", "--source", "langfuse", "--input", str(src), "--corpus", str(corpus)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Imported 1 cassette(s) from langfuse" in out
    assert list(corpus.glob(f"{IMPORT_PREFIX}*.json"))


def test_cli_import_auto_detect_and_skips_report(tmp_path: Path, capsys):
    src = _write_jsonl(
        tmp_path / "mixed.jsonl",
        [LANGFUSE_OBS, {"id": "bad", "type": "GENERATION", "input": None}],
    )
    code = cli_main(["import", "--input", str(src), "--corpus", str(tmp_path / "c")])
    assert code == 0
    captured = capsys.readouterr()
    assert "1 skipped" in captured.out
    assert "skipped" in captured.err  # the skip reason is surfaced on stderr


def test_cli_import_unreadable_is_usage_error(tmp_path: Path, capsys):
    code = cli_main(["import", "--source", "langfuse", "--input", str(tmp_path / "nope.json"),
                     "--corpus", str(tmp_path / "c")])
    assert code == 2
    assert "could not read" in capsys.readouterr().err
