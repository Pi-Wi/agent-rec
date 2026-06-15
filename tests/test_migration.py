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


def _baseline_interaction(
    prompt: str = PROMPT, answer_parts=("bl", "ue"), response_format=None
) -> CapturedInteraction:
    body = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": prompt}]}
    if response_format is not None:
        body["response_format"] = response_format
    final = _openai_chunk(None, finish="stop")
    final["usage"] = {"prompt_tokens": 7, "completion_tokens": 3}
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
        + [CapturedChunk(data=_sse(final)), CapturedChunk(data=b"data: [DONE]\n\n")],
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
    interaction = _baseline_interaction()
    interaction.metadata["category"] = "classify"
    await store.save(BASELINE_ID, interaction)


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
    assert cassette.metadata["category"] == "classify"  # baseline tag inherited

    assert report.all_passed
    assert report.live_count == 1 and report.cached_count == 0


async def test_category_and_tokens_flow_into_report(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact,fuzzy"), inner_transport=_anthropic_answer("Blue")
    )
    row = report.rows[0]
    assert row.category == "classify"
    # Baseline usage from the SSE stream; target usage from the mock JSON.
    assert (row.baseline_in_tokens, row.baseline_out_tokens) == (7, 3)
    assert (row.target_in_tokens, row.target_out_tokens) == (12, 2)

    totals = report.token_totals()
    assert totals is not None
    assert (totals.baseline_out, totals.target_out, totals.rows) == (3, 2, 1)
    assert totals.ratio == pytest.approx(2 / 3)

    breakdown = report.by_category()
    assert [cat.category for cat in breakdown] == ["classify"]
    assert breakdown[0].prompts == 1
    assert breakdown[0].aggregates[0].comparator == "exact"
    assert breakdown[0].tokens is not None


def _echo_transport() -> httpx.MockTransport:
    """Target stand-in that answers each prompt with a derived echo."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "model": TARGET_MODEL,
                "content": [{"type": "text", "text": f"echo: {prompt}"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 4},
            },
        )

    return httpx.MockTransport(handler)


async def test_concurrent_rows_keep_identities_separate(corpus: FileStore, monkeypatch):
    """Rows scored in parallel must not mix up cassette ids or lineage."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    prompts = [f"prompt number {i}" for i in range(6)]
    for i, prompt in enumerate(prompts):
        await corpus.save(f"b{i}", _baseline_interaction(prompt, answer_parts=("echo: ", prompt)))

    finished: list = []
    report = await run_migration(
        corpus,
        TARGET_MODEL,
        build_comparators("exact"),
        inner_transport=_echo_transport(),
        concurrency=4,
        progress=finished.append,
    )

    assert len(report.rows) == 6
    assert len(finished) == 6  # progress fired once per row
    for row in report.rows:
        assert row.status == "ok"
        # The target echoed exactly this row's prompt -> identities never crossed.
        assert row.target_text == f"echo: {row.prompt_text}"
    assert report.all_passed

    # Each migration cassette landed under the right id with the right lineage.
    for i, prompt in enumerate(prompts):
        cassette = await corpus.load(migration_id_for(f"b{i}", TARGET_MODEL))
        assert cassette.metadata["migrated_from"] == f"b{i}"
        payload = b"".join(chunk.data for chunk in cassette.chunks).decode()
        assert f"echo: {prompt}" in payload


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


async def test_response_format_baseline_migrates_to_anthropic(corpus: FileStore, monkeypatch):
    """JSON-mode baselines are translated (system-prompt emulation), not skipped."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    interaction = _baseline_interaction(
        answer_parts=('{"color": ', '"blue"}'), response_format={"type": "json_object"}
    )
    await corpus.save("json-mode", interaction)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": TARGET_MODEL,
                "content": [{"type": "text", "text": '{"color": "blue"}'}],
                "stop_reason": "end_turn",
            },
        )

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact,json"),
        inner_transport=httpx.MockTransport(handler),
    )
    row = report.rows[0]
    assert row.status == "ok"
    # Anthropic has no native JSON mode: emulated via system prompt, and the
    # OpenAI-only field must not leak into the Anthropic body.
    assert "response_format" not in seen["body"]
    assert "single JSON object" in seen["body"]["system"]
    assert report.all_passed


async def test_response_format_baseline_reemitted_for_openai_target(corpus: FileStore, monkeypatch):
    """Same-provider migration re-emits native response_format."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    interaction = _baseline_interaction(
        answer_parts=('{"color": ', '"blue"}'), response_format={"type": "json_object"}
    )
    await corpus.save("json-mode", interaction)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"color": "blue"}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    report = await run_migration(
        corpus, "gpt-4o", build_comparators("json"),
        inner_transport=httpx.MockTransport(handler),
    )
    row = report.rows[0]
    assert row.status == "ok"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "system" not in [m["role"] for m in seen["body"]["messages"]]
    assert report.all_passed


async def test_unsupported_baseline_becomes_skipped_row(corpus: FileStore, monkeypatch):
    # Tools are translatable now; images remain the honest skip.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    interaction = _baseline_interaction()
    body = json.loads(interaction.request.content)
    body["messages"][0]["content"] = [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
    ]
    interaction.request.content = json.dumps(body).encode()
    await corpus.save("imaged", interaction)

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_anthropic_answer()
    )
    row = next(r for r in report.rows if r.baseline_id == "imaged")
    assert row.status == "skipped"
    assert "image_url" in (row.reason or "")


async def test_failed_target_call_is_not_cached(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error"}})

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"),
        inner_transport=httpx.MockTransport(handler), retries=0,
    )
    row = report.rows[0]
    assert row.status == "error"
    assert "429" in (row.reason or "")
    # The failure was discarded, so a re-run gets a fresh live attempt.
    assert not await corpus.has(migration_id_for(BASELINE_ID, TARGET_MODEL))
    assert not report.all_passed


async def test_rate_limited_target_is_retried(corpus: FileStore, monkeypatch):
    """A 429 with Retry-After is retried; only the eventual 200 is cached."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(
                429,
                headers={"retry-after": "0"},
                json={"type": "error", "error": {"type": "rate_limit_error"}},
            )
        return httpx.Response(
            200,
            json={
                "model": TARGET_MODEL,
                "content": [{"type": "text", "text": "Blue"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 2},
            },
        )

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"),
        inner_transport=httpx.MockTransport(handler),
    )
    row = report.rows[0]
    assert calls["n"] == 3
    assert row.status == "ok"
    assert row.target_text == "Blue"
    assert sum("retried after HTTP 429" in note for note in row.notes) == 2
    # The cassette on disk is the successful answer, not a recorded 429.
    cassette = await corpus.load(migration_id_for(BASELINE_ID, TARGET_MODEL))
    assert b"Blue" in b"".join(chunk.data for chunk in cassette.chunks)


async def test_431_is_retried_as_transient(corpus: FileStore, monkeypatch):
    """431 (headers too large) is transient — headers are rebuilt fresh per row."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(431, headers={"retry-after": "0"}, text="Request headers too large")
        return httpx.Response(
            200,
            json={
                "model": TARGET_MODEL,
                "content": [{"type": "text", "text": "Blue"}],
                "stop_reason": "end_turn",
            },
        )

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"),
        inner_transport=httpx.MockTransport(handler),
    )
    row = report.rows[0]
    assert calls["n"] == 2
    assert row.status == "ok"
    assert row.target_text == "Blue"
    assert any("retried after HTTP 431" in note for note in row.notes)
    # The cassette on disk is the eventual 200, not the recorded 431.
    cassette = await corpus.load(migration_id_for(BASELINE_ID, TARGET_MODEL))
    assert b"Blue" in b"".join(chunk.data for chunk in cassette.chunks)


async def test_non_retryable_4xx_stays_fatal_with_body_snippet(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"type": "error", "error": {"message": "bad sampling param"}})

    report = await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"),
        inner_transport=httpx.MockTransport(handler),
    )
    row = report.rows[0]
    assert calls["n"] == 1  # no retries for a request-shaped failure
    assert row.status == "error"
    assert "400" in (row.reason or "")
    assert "bad sampling param" in (row.reason or "")  # body snippet surfaced
    assert not await corpus.has(migration_id_for(BASELINE_ID, TARGET_MODEL))


async def test_judge_verdicts_are_cached_in_corpus_and_replayed_offline(
    corpus: FileStore, monkeypatch
):
    """End-to-end: migrate online with a judge, then re-report fully offline."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    await _seed_baseline(corpus)

    judge_calls = {"n": 0}

    def judge_handler(request: httpx.Request) -> httpx.Response:
        judge_calls["n"] += 1
        verdict = '{"equivalent": true, "score": 0.9, "reason": "same color"}'
        return httpx.Response(
            200,
            json={
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": verdict}],
                "stop_reason": "end_turn",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(judge_handler)) as judge_http:
        comparators = build_comparators("exact,judge", http=judge_http, store=corpus)
        report = await run_migration(
            corpus, TARGET_MODEL, comparators, inner_transport=_anthropic_answer("Blue")
        )
    assert judge_calls["n"] == 1
    judge_result = next(c for c in report.rows[0].comparisons if c.comparator == "judge")
    assert judge_result.passed is True and "[cached]" not in judge_result.detail
    judge_ids = [i for i in corpus.ids() if i.startswith("judge__")]
    assert len(judge_ids) == 1  # the verdict is now a corpus cassette

    # Offline re-run: no key, no socket — the verdict replays from the corpus.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("offline run must not touch the network")

    async with httpx.AsyncClient(transport=httpx.MockTransport(explode)) as judge_http:
        comparators = build_comparators("exact,judge", http=judge_http, store=corpus, offline=True)
        offline_report = await run_migration(
            corpus, TARGET_MODEL, comparators, offline=True,
            inner_transport=_raising_transport(),
        )
    row = offline_report.rows[0]
    assert row.status == "ok" and row.cached is True
    judge_result = next(c for c in row.comparisons if c.comparator == "judge")
    assert judge_result.passed is True
    assert "[cached]" in judge_result.detail
    # Judge cassettes are tooling artifacts, never baselines.
    assert [r.baseline_id for r in offline_report.rows] == [BASELINE_ID]


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
# --min-pass threshold gates
# ---------------------------------------------------------------------------


def _gate_report(min_pass: dict, json_passes: int = 9, json_fails: int = 1) -> "MigrationReport":
    """Hand-built report: N ok rows scored by json (mixed) and fuzzy (all failing)."""
    from agentrec import ComparisonResult, MigrationReport, RowResult

    rows = []
    for i in range(json_passes + json_fails):
        passed = i < json_passes
        rows.append(
            RowResult(
                semantic_key=f"k{i}",
                baseline_id=f"b{i}",
                migration_id=f"m{i}",
                prompt_preview=f"p{i}",
                comparisons=[
                    ComparisonResult("json", 1.0 if passed else 0.5, passed, ""),
                    ComparisonResult("fuzzy", 0.4, False, ""),
                ],
            )
        )
    return MigrationReport(
        target_model="t", target_provider="anthropic", corpus="c", generated_at="now",
        comparator_names=["json", "fuzzy"], rows=rows, min_pass=min_pass,
    )


def test_min_pass_gates_on_pass_rate_and_ignores_informational_comparators():
    # json 9/10 = 90%: meets a 0.9 threshold even though fuzzy fails every row.
    report = _gate_report({"json": 0.9})
    assert report.all_passed is False  # all-or-nothing still red
    assert report.strict_passed is True
    (gate,) = report.gates()
    assert gate.comparator == "json" and gate.passed is True
    assert gate.pass_rate == pytest.approx(0.9)
    assert "9/10" in gate.detail

    # A higher bar fails.
    report = _gate_report({"json": 0.95})
    assert report.strict_passed is False
    (gate,) = report.gates()
    assert gate.passed is False and "<" in gate.detail

    # Naming the failing comparator gates on it.
    report = _gate_report({"json": 0.9, "fuzzy": 0.6})
    assert report.strict_passed is False
    assert [g.passed for g in report.gates()] == [True, False]


def test_min_pass_comparator_errors_fail_the_gate():
    from agentrec import ComparisonResult

    report = _gate_report({"json": 0.5})
    report.rows[0].comparisons[0] = ComparisonResult("json", 0.0, None, "boom", error=True)
    (gate,) = report.gates()
    assert gate.passed is False
    assert gate.errors == 1
    assert "error" in gate.detail
    assert report.strict_passed is False


def test_min_pass_empty_run_is_not_a_pass():
    report = _gate_report({"json": 0.0})
    report.rows.clear()
    assert report.strict_passed is False

    # An errored row also fails the gate, same as all-or-nothing --strict.
    report = _gate_report({"json": 0.0})
    report.rows[0].status = "error"
    report.rows[0].reason = "target call failed"
    assert report.strict_passed is False


def test_min_pass_unknown_comparator_fails_closed():
    report = _gate_report({"judge": 0.5})
    (gate,) = report.gates()
    assert gate.passed is False and "did not run" in gate.detail
    assert report.strict_passed is False


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
    assert "## By category" in markdown
    assert "classify" in markdown
    assert "**Output tokens:**" in markdown

    html = render_html(report)
    assert html.startswith("<!doctype html>")
    assert "class='pass'" in html
    assert "Blue" in html
    assert "By category" in html
    assert "class='tag'" in html  # category chips in the tables

    console = render_console(report)
    assert console.isascii(), "console output must be ASCII-safe on Windows terminals"
    assert "1 prompts" in console
    assert "out tokens" in console


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


def test_cli_strict_min_pass_gates_and_renders(corpus: FileStore, monkeypatch, tmp_path: Path, capsys):
    """--strict --min-pass gates on the named comparator's pass rate only."""
    import asyncio

    # Target answers "Red" for the "blue" baseline: exact and fuzzy both fail.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    asyncio.run(_seed_baseline(corpus))
    asyncio.run(
        run_migration(
            corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_anthropic_answer("Red")
        )
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    base_args = [
        "report", "--corpus", str(corpus.root), "--target", TARGET_MODEL,
        "--compare", "exact,fuzzy", "--out", str(tmp_path / "rep"), "--strict",
    ]
    # All-or-nothing --strict: red.
    assert cli_main(base_args) == 1
    # Gate only on fuzzy with a 0.0 bar: exact's failure is informational.
    assert cli_main(base_args + ["--min-pass", "fuzzy=0.0"]) == 0
    # Gate on exact at 1.0: red again.
    assert cli_main(base_args + ["--min-pass", "exact=1.0"]) == 1
    out = capsys.readouterr().out
    assert "gate exact:" in out and "FAIL" in out

    # The written reports surface thresholds and rates.
    markdown = (tmp_path / "rep.md").read_text(encoding="utf-8")
    assert "## Strict gate" in markdown and "100%" in markdown
    html = (tmp_path / "rep.html").read_text(encoding="utf-8")
    assert "Strict gate" in html

    # Malformed or unknown --min-pass flags are usage errors (exit 2).
    assert cli_main(base_args + ["--min-pass", "exact"]) == 2
    assert cli_main(base_args + ["--min-pass", "exact=1.5"]) == 2
    assert cli_main(base_args + ["--min-pass", "judge=0.5"]) == 2


def test_cli_report_accepts_json_comparator_offline(
    corpus: FileStore, monkeypatch, capsys, tmp_path: Path
):
    """`json` is offline: the report command's gate must let it through."""
    import asyncio

    asyncio.run(_completed_report(corpus, monkeypatch))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # No --strict: this corpus's answers are plain words, so the json
    # comparator degrades to an errored result per row — which is exactly
    # what --strict is meant to flag. Here we only prove the gate accepts it.
    # --out-dir keeps the report under tmp_path (not the repo root).
    out_dir = tmp_path / "reports"
    code = cli_main(
        ["report", "--corpus", str(corpus.root), "--target", TARGET_MODEL,
         "--compare", "json", "--out-dir", str(out_dir)]
    )
    assert code == 0
    assert "json" in capsys.readouterr().out
    assert list(out_dir.glob("migration-report__*"))


def test_cli_report_out_dir_default_and_dotted_target(
    corpus: FileStore, monkeypatch, capsys, tmp_path: Path
):
    """Reports land in --out-dir, and a dotted target id is not truncated."""
    import asyncio

    asyncio.run(_seed_baseline(corpus))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    out_dir = tmp_path / "out"
    # gemini-2.5-flash has no recorded migration cassette here, so rows skip —
    # but the report files are still written, which is what we're checking.
    code = cli_main(
        ["report", "--corpus", str(corpus.root), "--target", "gemini-2.5-flash",
         "--compare", "exact", "--format", "both", "--out-dir", str(out_dir)]
    )
    assert code == 0
    names = sorted(p.name for p in out_dir.glob("*"))
    # Both formats written, and the dot in "2.5" did NOT truncate the name.
    assert any(n.endswith(".md") and "gemini-2.5-flash" in n for n in names)
    assert any(n.endswith(".html") and "gemini-2.5-flash" in n for n in names)


def test_cli_report_rejects_online_comparators(corpus: FileStore, capsys):
    # judge is allowed offline since 0.5 (cached verdicts); embedding is not.
    code = cli_main(
        ["report", "--corpus", str(corpus.root), "--target", TARGET_MODEL, "--compare", "exact,embedding"]
    )
    assert code == 2
    assert "embedding" in capsys.readouterr().err


def test_cli_annotate_smoke(corpus: FileStore, capsys):
    import asyncio

    asyncio.run(_seed_baseline(corpus))
    code = cli_main(["annotate", "--corpus", str(corpus.root)])
    assert code == 0
    assert "Annotated 1" in capsys.readouterr().out
    raw = json.loads((corpus.root / f"{BASELINE_ID}.json").read_text(encoding="utf-8"))
    assert raw["metadata"]["provider"] == "openai"
