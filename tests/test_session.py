"""
Offline tests for the high-level facade (async_client + cassette) and keying.

No network or API key required: a canned-SSE transport stands in for the
upstream so record/replay/auto can be exercised deterministically.  The OpenAI
SDK is used only as a convenient SSE parser — the mechanism under test is
provider-neutral.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

from agentrec import FileStore, InMemoryStore, async_client, cassette


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _stream_body(text: str, model: str = "gpt-4o-mini") -> bytes:
    """A minimal OpenAI chat-completion SSE stream emitting *text*."""
    frames = [
        _sse(
            {
                "id": "chatcmpl-x",
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}}],
            }
        ),
        _sse(
            {
                "id": "chatcmpl-x",
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        ),
        b"data: [DONE]\n\n",
    ]
    return b"".join(frames)


class _CannedSSE(httpx.AsyncBaseTransport):
    """Upstream stand-in: returns a fixed SSE body and counts how often it ran."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=self.body
        )

    async def aclose(self) -> None:
        pass


class _NoNetwork(httpx.AsyncBaseTransport):
    """Fails loudly if a replay path ever tries to reach the network."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay must not touch the network")

    async def aclose(self) -> None:
        pass


async def _ask(http: httpx.AsyncClient, prompt: str) -> str:
    client = AsyncOpenAI(api_key="fake-key", http_client=http)
    stream = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    content = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            content += chunk.choices[0].delta.content
    return content


@pytest.mark.asyncio
async def test_record_then_replay_via_facade(tmp_path: Path) -> None:
    """cassette(record) tees through the upstream; cassette(replay) is offline."""
    store = FileStore(tmp_path)
    upstream = _CannedSSE(_stream_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="record"):
            recorded = await _ask(http, "say hi")
    assert recorded == "Hello world"
    assert upstream.calls == 1

    # Replay through a client that would raise on any real network access.
    async with async_client(inner=_NoNetwork()) as http:
        async with cassette(store, mode="replay"):
            replayed = await _ask(http, "say hi")
    assert replayed == "Hello world"


@pytest.mark.asyncio
async def test_auto_records_once_then_replays(tmp_path: Path) -> None:
    """auto mode records on first sight of a request and replays thereafter."""
    store = FileStore(tmp_path)
    upstream = _CannedSSE(_stream_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="auto"):
            first = await _ask(http, "say hi")
            second = await _ask(http, "say hi")  # same request → replayed

    assert first == second == "Hello world"
    assert upstream.calls == 1, "second identical call should replay, not re-record"
    assert len(store) == 1


@pytest.mark.asyncio
async def test_auto_keying_distinguishes_prompts(tmp_path: Path) -> None:
    """Different prompts get different cassettes; identical ones share one."""
    store = FileStore(tmp_path)
    upstream = _CannedSSE(_stream_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="auto"):
            await _ask(http, "prompt A")
            await _ask(http, "prompt B")
            await _ask(http, "prompt A")  # repeat → no new cassette

    assert upstream.calls == 2
    assert len(store) == 2


@pytest.mark.asyncio
async def test_record_captures_provenance_metadata(tmp_path: Path) -> None:
    """A recording carries provider/model/semantic_key/recorded_at for the corpus."""
    store = FileStore(tmp_path)
    upstream = _CannedSSE(_stream_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="record", id="probe"):
            await _ask(http, "say hi")

    interaction = await store.load("probe")
    meta = interaction.metadata
    assert meta["provider"] == "openai"
    assert meta["model"] == "gpt-4o-mini"
    assert meta["semantic_key"] and isinstance(meta["semantic_key"], str)
    assert "recorded_at" in meta


@pytest.mark.asyncio
async def test_cassette_metadata_is_stamped_on_recordings(tmp_path: Path) -> None:
    """metadata= on a cassette scope lands in every interaction it records."""
    store = FileStore(tmp_path)
    upstream = _CannedSSE(_stream_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="record", id="tagged", metadata={"category": "classify"}):
            await _ask(http, "say hi")

    interaction = await store.load("tagged")
    assert interaction.metadata["category"] == "classify"
    assert interaction.metadata["provider"] == "openai"  # fingerprint fields intact


@pytest.mark.asyncio
async def test_decorator_form_scopes_recording(tmp_path: Path) -> None:
    """@cassette wraps an async function the same way the context manager does."""
    store = FileStore(tmp_path)
    upstream = _CannedSSE(_stream_body("Hello world"))
    http = async_client(inner=upstream)

    @cassette(store, mode="auto")
    async def ask(prompt: str) -> str:
        return await _ask(http, prompt)

    async with http:
        assert await ask("say hi") == "Hello world"
    assert len(store) == 1


@pytest.mark.asyncio
async def test_no_scope_passes_through(tmp_path: Path) -> None:
    """Outside any cassette scope, async_client just hits the (stub) network."""
    store = InMemoryStore()
    upstream = _CannedSSE(_stream_body("Hello world"))

    async with async_client(inner=upstream) as http:
        out = await _ask(http, "say hi")  # no cassette → straight to upstream

    assert out == "Hello world"
    assert upstream.calls == 1
    assert not await store.has("anything"), "nothing should be recorded without a scope"
