"""
Tests for the 0.3 hardening pass, fully offline.

Covers: prompt-level semantic keys, error responses not being cached,
the sync client/transports, collision-proof cassette filenames, opt-in
response scrubbing, SSE spec compliance, judge verdict extraction, registry
override semantics, the strict-gate fix, truncation flagging, and
Retry-After date parsing.
"""
from __future__ import annotations

import datetime as dt
import json
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from agentrec import (
    AutoTransport,
    FileStore,
    InMemoryStore,
    JudgeComparator,
    MigrationReport,
    RecordingTransport,
    RowResult,
    build_comparators,
    cassette,
    fingerprint,
    run_migration,
    sync_client,
)
from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.migration import _retry_delay
from agentrec.providers import DecodedResponse, adapter_for_host, adapter_for_model
from agentrec.providers import adapter_for_provider, register, sse_data_lines


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _baseline(prompt: str = "Say blue.") -> CapturedInteraction:
    """A minimal recorded OpenAI streaming interaction answering 'blue'."""
    body = {
        "model": "gpt-4o-mini",
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
    }
    chunk = {
        "id": "chatcmpl-x",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": {"content": "blue"}, "finish_reason": None}],
    }
    final = {
        "id": "chatcmpl-x",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return CapturedInteraction(
        request=CapturedRequest(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers=[(b"content-type", b"application/json")],
            content=json.dumps(body).encode(),
        ),
        response_status=200,
        response_headers=[(b"content-type", b"text/event-stream")],
        response_extensions={},
        chunks=[
            CapturedChunk(data=_sse(chunk)),
            CapturedChunk(data=_sse(final)),
            CapturedChunk(data=b"data: [DONE]\n\n"),
        ],
    )


# ---------------------------------------------------------------------------
# Keying: semantic_key is prompt-level, cassette_id is request-level
# ---------------------------------------------------------------------------


def _fp(body: dict):
    return fingerprint(
        httpx.Request("POST", "https://api.openai.com/v1/chat/completions", json=body)
    )


def test_semantic_key_ignores_sampling_params():
    base = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    sampled = {**base, "temperature": 0.9, "max_tokens": 256, "seed": 7, "user": "u1"}

    assert _fp(base).semantic_key == _fp(sampled).semantic_key
    # ...but record/replay still distinguishes the two requests.
    assert _fp(base).cassette_id != _fp(sampled).cassette_id


def test_semantic_key_still_distinguishes_prompts():
    base = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    other = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "bye"}]}
    assert _fp(base).semantic_key != _fp(other).semantic_key


def test_semantic_key_groups_across_providers():
    """The same logical prompt hashes identically regardless of provider dialect."""
    openai_fp = fingerprint(
        httpx.Request(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "stream": True,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": "Be terse."},
                    {"role": "user", "content": "hi"},
                ],
            },
        )
    )
    anthropic_fp = fingerprint(
        httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 64,
                "system": "Be terse.",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    )
    assert openai_fp.semantic_key == anthropic_fp.semantic_key
    assert openai_fp.cassette_id != anthropic_fp.cassette_id


def test_semantic_key_fallback_for_unknown_hosts_still_ignores_sampling():
    """Requests no adapter understands fall back to the body hash minus sampling."""

    def fp(body: dict):
        return fingerprint(
            httpx.Request("POST", "https://api.example.test/v1/generate", json=body)
        )

    base = {"model": "m", "input": "hi"}  # not a chat-shaped body
    sampled = {**base, "temperature": 0.5, "seed": 3}
    assert fp(base).semantic_key == fp(sampled).semantic_key
    assert fp(base).cassette_id != fp(sampled).cassette_id


# ---------------------------------------------------------------------------
# Transport: error responses are not cached
# ---------------------------------------------------------------------------


async def test_error_responses_are_not_recorded_by_default():
    store = InMemoryStore()
    transport = RecordingTransport(
        httpx.MockTransport(lambda request: httpx.Response(500, json={"error": "boom"})),
        store,
        key="err",
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json={"x": 1})
    # The caller still sees the failure; the store never does.
    assert response.status_code == 500
    assert response.json() == {"error": "boom"}
    assert not await store.has("err")


async def test_error_responses_recorded_when_opted_in():
    store = InMemoryStore()
    transport = RecordingTransport(
        httpx.MockTransport(lambda request: httpx.Response(404, json={"error": "nope"})),
        store,
        key="err",
        record_errors=True,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        await client.post("https://api.openai.com/v1/chat/completions", json={"x": 1})
    assert await store.has("err")
    assert (await store.load("err")).response_status == 404


async def test_auto_mode_retries_live_after_an_uncached_failure():
    store = InMemoryStore()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, json={"ok": True})

    transport = AutoTransport(httpx.MockTransport(handler), store, key="k")
    async with httpx.AsyncClient(transport=transport) as client:
        first = await client.post("https://api.test/v1", json={"a": 1})
        second = await client.post("https://api.test/v1", json={"a": 1})
        third = await client.post("https://api.test/v1", json={"a": 1})

    assert first.status_code == 503
    assert second.status_code == 200
    assert third.status_code == 200
    assert calls["n"] == 2, "the failure was not cached; the success was"


# ---------------------------------------------------------------------------
# Sync client / transports
# ---------------------------------------------------------------------------


class _NoNetworkSync(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay must not touch the network")


def test_sync_client_record_then_replay(tmp_path: Path):
    store = FileStore(tmp_path)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"echo": json.loads(request.content)["q"]})

    with sync_client(inner=httpx.MockTransport(handler)) as http:
        with cassette(store, mode="auto"):
            first = http.post("https://api.example.test/v1/echo", json={"q": "hi"}).json()
            second = http.post("https://api.example.test/v1/echo", json={"q": "hi"}).json()
    assert first == second == {"echo": "hi"}
    assert calls["n"] == 1, "second identical call must replay, not re-record"

    # Replay leg is fully offline.
    with sync_client(inner=_NoNetworkSync()) as http:
        with cassette(store, mode="replay"):
            replayed = http.post("https://api.example.test/v1/echo", json={"q": "hi"}).json()
    assert replayed == {"echo": "hi"}


def test_cassette_decorates_sync_functions(tmp_path: Path):
    store = FileStore(tmp_path)
    upstream = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    http = sync_client(inner=upstream)

    @cassette(store, mode="auto")
    def ask() -> dict:
        return http.post("https://api.example.test/v1/x", json={"q": 1}).json()

    with http:
        assert ask() == {"ok": True}
    assert len(store) == 1


# ---------------------------------------------------------------------------
# FileStore: filename collisions and response scrubbing
# ---------------------------------------------------------------------------


async def test_sanitized_ids_do_not_collide(tmp_path: Path):
    """Ids that sanitize to the same filename must stay distinct on disk."""
    store = FileStore(tmp_path)
    await store.save("a/b", _baseline("first prompt"))
    await store.save("a_b", _baseline("second prompt"))

    assert len(store) == 2
    assert b"first prompt" in (await store.load("a/b")).request.content
    assert b"second prompt" in (await store.load("a_b")).request.content


async def test_response_chunk_scrubbing_is_opt_in(tmp_path: Path):
    secret = "sk-abcdEFGH1234567890zzzz"
    interaction = _baseline()
    interaction.response_headers = [(b"content-type", b"application/json")]
    interaction.chunks = [CapturedChunk(data=json.dumps({"note": secret}).encode())]

    # Default: response chunks are the replay source of truth — verbatim.
    default_store = FileStore(tmp_path / "default")
    await default_store.save("x", interaction)
    assert secret in default_store._path("x").read_text(encoding="utf-8")

    # Opt-in: chunk text is scrubbed best-effort before writing.
    scrubbed_store = FileStore(tmp_path / "scrubbed", scrub_response_body=True)
    await scrubbed_store.save("x", interaction)
    raw = scrubbed_store._path("x").read_text(encoding="utf-8")
    assert secret not in raw
    assert "[REDACTED-OPENAI-KEY]" in raw


# ---------------------------------------------------------------------------
# SSE spec compliance
# ---------------------------------------------------------------------------


def test_sse_data_lines_strips_exactly_one_leading_space():
    payload = b"data:  two spaces\n\ndata:none\n\ndata\n\n"
    # One space is field-separator (stripped); the second is payload (kept).
    assert sse_data_lines(payload) == [" two spaces", "none", ""]


# ---------------------------------------------------------------------------
# Judge verdict extraction
# ---------------------------------------------------------------------------


async def test_judge_prefers_verdict_shaped_object(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    reply = (
        'Using rubric {"weights": {"style": 0}} I conclude: '
        '{"equivalent": false, "score": 0.25, "reason": "different facts"}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": reply}],
                "stop_reason": "end_turn",
            },
        )

    def _resp(text: str) -> DecodedResponse:
        return DecodedResponse(provider="openai", model="m", text=text)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await JudgeComparator(http, judge_model="claude-opus-4-8").compare(
            "p", _resp("a"), _resp("b")
        )
    # The decoy rubric object came first; the verdict object must win.
    assert result.passed is False
    assert result.score == pytest.approx(0.25)
    assert result.detail == "different facts"


# ---------------------------------------------------------------------------
# Registry: later registrations override built-ins
# ---------------------------------------------------------------------------


def test_later_registration_overrides_builtin():
    from agentrec.providers import _ADAPTERS, OpenAIAdapter

    class CustomOpenAI(OpenAIAdapter):
        pass

    custom = CustomOpenAI()
    register(custom)
    try:
        assert adapter_for_provider("openai") is custom
        assert adapter_for_model("gpt-4o-mini") is custom
        assert adapter_for_host("api.openai.com") is custom
    finally:
        _ADAPTERS.remove(custom)
    assert not isinstance(adapter_for_provider("openai"), CustomOpenAI)


# ---------------------------------------------------------------------------
# Migration: strict gate, truncation flag, Retry-After dates
# ---------------------------------------------------------------------------


def test_all_skipped_run_is_not_a_pass():
    row = RowResult(
        semantic_key="k",
        baseline_id="b",
        migration_id="m",
        prompt_preview="p",
        status="skipped",
        reason="offline",
    )
    report = MigrationReport(
        target_model="t",
        target_provider="anthropic",
        corpus="",
        generated_at="",
        comparator_names=["exact"],
        rows=[row],
    )
    assert report.all_passed is False


async def test_truncated_target_response_is_flagged(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = FileStore(tmp_path / "corpus")
    await store.save("b", _baseline())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "claude-haiku-4-5",
                "content": [{"type": "text", "text": "blu"}],
                "stop_reason": "max_tokens",
                "usage": {"input_tokens": 5, "output_tokens": 64},
            },
        )

    report = await run_migration(
        store,
        "claude-haiku-4-5",
        build_comparators("exact"),
        inner_transport=httpx.MockTransport(handler),
    )
    row = report.rows[0]
    assert row.status == "ok"
    assert any("truncated" in note for note in row.notes)


def test_retry_after_http_date_is_honoured():
    when = format_datetime(
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30), usegmt=True
    )
    response = httpx.Response(429, headers={"retry-after": when})
    delay = _retry_delay(response, attempt=0)
    assert 20.0 <= delay <= 31.0


def test_retry_after_garbage_falls_back_to_exponential():
    response = httpx.Response(429, headers={"retry-after": "soonish"})
    assert _retry_delay(response, attempt=2) == 4.0
