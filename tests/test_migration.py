"""
End-to-end migration tests, fully offline.

A synthetic OpenAI streaming baseline cassette is migrated cross-provider to
an Anthropic target served by a mock transport.  The tests prove the core
contracts: deterministic migration cassette ids, pinned semantic keys and
``migrated_from`` lineage, corpus-cached re-runs (no network), failed calls
not poisoning the cache, summary blocks, annotate, report rendering, and the
CLI's offline ``report`` path.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agentrec import (
    AutoTransport,
    FileStore,
    InMemoryStore,
    RecordingTransport,
    build_comparators,
    fingerprint_of,
    migration_id_for,
    run_migration,
)
from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.cli import main as cli_main
from agentrec.migration import annotate_corpus
from agentrec.report import render_console, render_html, render_markdown

BASELINE_ID = "ticket-color"
TARGET_MODEL = "claude-haiku-4-5"
PROMPT = "Classify the dominant color in 'a clear summer sky': answer with one word."


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _openai_chunk(content=None, finish=None) -> dict:
    delta = {"content": content} if content is not None else {}
    return {
        "id": "chatcmpl-x",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _baseline_interaction(prompt: str = PROMPT, answer_parts=("bl", "ue")) -> CapturedInteraction:
    body = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": prompt}]}
    return CapturedInteraction(
        request=CapturedRequest(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers=[(b"content-type", b"application/json")],
            content=json.dumps(body).encode(),
        ),
        response_status=200,
        response_headers=[(b"content-type", b"text/event-stream; charset=utf-8")],
        response_extensions={},
        chunks=[CapturedChunk(data=_sse(_openai_chunk(part))) for part in answer_parts]
        + [CapturedChunk(data=_sse(_openai_chunk(None, finish="stop"))), CapturedChunk(data=b"data: [DONE]\n\n")],
    )


def _anthropic_answer(text: str = "Blue") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.host == "api.anthropic.com"
        assert body["model"] == TARGET_MODEL
        assert "stream" not in body and "temperature" not in body
        return httpx.Response(
            200,
            json={
                "model": TARGET_MODEL,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 2},
            },
        )

    return httpx.MockTransport(handler)


def _raising_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("cached run must not touch the network")

    return httpx.MockTransport(handler)


@pytest.fixture
def corpus(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "corpus")


async def _seed_baseline(store: FileStore) -> None:
    await store.save(BASELINE_ID, _baseline_interaction())


# ---------------------------------------------------------------------------
# transport extra_metadata
# ---------------------------------------------------------------------------


async def test_recording_transport_merges_extra_metadata():
    store = InMemoryStore()
    transport = RecordingTransport(
        _anthropic_answer(), store, key="fixed-id", extra_metadata={"migrated_from": "x", "semantic_key": "pinned"}
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": TARGET_MODEL, "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]},
        )
        await response.aread()
    saved = await store.load("fixed-id")
    assert saved.metadata["migrated_from"] == "x"
    assert saved.metadata["semantic_key"] == "pinned"  # override wins over fingerprint
    assert saved.metadata["provider"] == "anthropic"  # fingerprint fields still present


# ---------------------------------------------------------------------------
# store summary block
# ---------------------------------------------------------------------------


async def test_filestore_writes_summary_first_and_ignores_it_on_load(corpus: FileStore):
    await _seed_baseline(corpus)
    raw = json.loads((corpus.root / f"{BASELINE_ID}.json").read_text(encoding="utf-8"))
    assert list(raw)[0] == "summary"
    assert raw["summary"]["prompt"] == PROMPT
    assert raw["summary"]["response"] == "blue"
    assert raw["summary"]["provider"] == "openai"
    # Round-trip: summary is derived, the interaction loads from raw parts.
    from agentrec import decode_interaction

    loaded = await corpus.load(BASELINE_ID)
    assert decode_interaction(loaded).text == "blue"


async def test_annotate_backfills_legacy_cassette(corpus: FileStore):
    # Hand-write a legacy-style cassette: no metadata, no summary.
    legacy = {
        "request": {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "headers": [],
            "content": json.dumps(
                {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Say hi."}]}
            ),
        },
        "response_status": 200,
        "response_headers": [["content-type", "application/json"]],
        "response_extensions": {},
        "chunks": [
            {
                "data": json.dumps(
                    {
                        "model": "gpt-4o-mini",
                        "choices": [
                            {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
                        ],
                    }
                ),
                "timestamp_offset": 0.0,
            }
        ],
    }
    (corpus.root / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")

    annotated = await annotate_corpus(corpus)
    assert "legacy" in annotated
    raw = json.loads((corpus.root / "legacy.json").read_text(encoding="utf-8"))
    assert list(raw)[0] == "summary"
    assert raw["metadata"]["provider"] == "openai"
    assert raw["metadata"]["model"] == "gpt-4o-mini"
    assert raw["metadata"]["semantic_key"]


# ---------------------------------------------------------------------------
# migration end-to-end
# ---------------------------------------------------------------------------


async def test_migration_end_to_end_cross_provider(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)

    comparators = build_comparators("exact,fuzzy")
    report = await run_migration(
        corpus, TARGET_MODEL, comparators, inner_transport=_anthropic_answer("Blue")
    )

    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.status == "ok"
    assert row.cached is False
    assert row.baseline_text == "blue"
    assert row.target_text == "Blue"
    assert row.baseline_model == "gpt-4o-mini"

    exact = next(c for c in row.comparisons if c.comparator == "exact")
    assert exact.passed is True  # "blue" == "Blue" after normalization
    fuzzy = next(c for c in row.comparisons if c.comparator == "fuzzy")
    assert fuzzy.score == pytest.approx(1.0)

    # The target's answer is now a corpus cassette with pinned identity.
    migration_id = migration_id_for(BASELINE_ID, TARGET_MODEL)
    assert row.migration_id == migration_id
    assert await corpus.has(migration_id)
    cassette = await corpus.load(migration_id)
    baseline_fp = fingerprint_of(_baseline_interaction())
    assert cassette.metadata["migrated_from"] == BASELINE_ID
    assert cassette.metadata["semantic_key"] == baseline_fp.semantic_key
    assert cassette.metadata["baseline_model"] == "gpt-4o-mini"
    assert cassette.metadata["model"] == TARGET_MODEL

    assert report.all_passed
    assert report.live_count == 1 and report.cached_count == 0


async def test_migration_rerun_is_served_from_corpus(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)
    await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_anthropic_answer("Blue")
    )

    # Second run: no API key, a transport that explodes on use — must still work.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_raising_transport()
    )
    row = report.rows[0]
    assert row.status == "ok"
    assert row.cached is True
    assert row.target_text == "Blue"


async def test_offline_mode_skips_unrecorded_targets(corpus: FileStore):
    await _seed_baseline(corpus)
    report = await run_migration(corpus, TARGET_MODEL, build_comparators("exact"), offline=True)
    row = report.rows[0]
    assert row.status == "skipped"
    assert "no recorded migration response" in (row.reason or "")


async def test_unsupported_baseline_becomes_skipped_row(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    interaction = _baseline_interaction()
    body = json.loads(interaction.request.content)
    body["tools"] = [{"type": "function", "function": {"name": "f"}}]
    interaction.request.content = json.dumps(body).encode()
    await corpus.save("tooled", interaction)

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_anthropic_answer()
    )
    row = next(r for r in report.rows if r.baseline_id == "tooled")
    assert row.status == "skipped"
    assert "tools" in (row.reason or "")


async def test_failed_target_call_is_not_cached(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error"}})

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=httpx.MockTransport(handler)
    )
    row = report.rows[0]
    assert row.status == "error"
    assert "429" in (row.reason or "")
    # The failure was discarded, so a re-run gets a fresh live attempt.
    assert not await corpus.has(migration_id_for(BASELINE_ID, TARGET_MODEL))
    assert not report.all_passed


async def test_migration_cassettes_are_excluded_as_baselines(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)
    await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_anthropic_answer()
    )
    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_raising_transport()
    )
    assert [row.baseline_id for row in report.rows] == [BASELINE_ID]


# ---------------------------------------------------------------------------
# rendering + CLI
# ---------------------------------------------------------------------------


async def _completed_report(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)
    return await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact,fuzzy"), inner_transport=_anthropic_answer("Blue")
    )


async def test_render_markdown_html_console(corpus: FileStore, monkeypatch):
    report = await _completed_report(corpus, monkeypatch)

    markdown = render_markdown(report)
    assert f"→ {TARGET_MODEL}" in markdown
    assert "| exact |" in markdown or "| exact " in markdown
    assert "<details><summary>Prompt</summary>" in markdown
    assert PROMPT in markdown

    html = render_html(report)
    assert html.startswith("<!doctype html>")
    assert "class='pass'" in html
    assert "Blue" in html

    console = render_console(report)
    assert console.isascii(), "console output must be ASCII-safe on Windows terminals"
    assert "1 prompts" in console


def test_cli_report_smoke(corpus: FileStore, monkeypatch, tmp_path: Path, capsys):
    # CLI is sync (it owns asyncio.run), so this test must be sync too.
    import asyncio

    asyncio.run(_completed_report(corpus, monkeypatch))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    out_base = tmp_path / "rep"
    code = cli_main(
        [
            "report",
            "--corpus", str(corpus.root),
            "--target", TARGET_MODEL,
            "--compare", "exact,fuzzy",
            "--format", "both",
            "--out", str(out_base),
            "--strict",
        ]
    )
    assert code == 0
    assert (tmp_path / "rep.md").exists()
    assert (tmp_path / "rep.html").exists()
    assert "Report written" in capsys.readouterr().out


def test_cli_report_rejects_online_comparators(corpus: FileStore, capsys):
    code = cli_main(
        ["report", "--corpus", str(corpus.root), "--target", TARGET_MODEL, "--compare", "exact,judge"]
    )
    assert code == 2
    assert "judge" in capsys.readouterr().err


def test_cli_annotate_smoke(corpus: FileStore, capsys):
    import asyncio

    asyncio.run(_seed_baseline(corpus))
    code = cli_main(["annotate", "--corpus", str(corpus.root)])
    assert code == 0
    assert "Annotated 1" in capsys.readouterr().out
    raw = json.loads((corpus.root / f"{BASELINE_ID}.json").read_text(encoding="utf-8"))
    assert raw["metadata"]["provider"] == "openai"
