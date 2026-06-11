"""
Non-streaming response support: record and replay of plain JSON responses.

All tests are fully offline — no API key required.  A _CannedJSON transport
stands in for the upstream, returning a minimal application/json body.  The
OpenAI SDK is used as a convenient JSON parser; the mechanism under test is
provider-neutral.

These tests confirm that _TeeStream / _ReplayStream work equally well for
single-chunk JSON bodies as they do for multi-chunk SSE bodies.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

from agentrec import FileStore, InMemoryStore, async_client, cassette


def _json_body(content: str = "Hello world", model: str = "gpt-4o-mini") -> bytes:
    """Minimal valid OpenAI non-streaming chat completion response."""
    return json.dumps(
        {
            "id": "chatcmpl-x",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
    ).encode()


class _CannedJSON(httpx.AsyncBaseTransport):
    """Returns a fixed JSON body and counts how often it was called."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(
            200, headers={"content-type": "application/json"}, content=self.body
        )

    async def aclose(self) -> None:
        pass


class _NoNetwork(httpx.AsyncBaseTransport):
    """Fails loudly if replay ever tries to reach the network."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay must not touch the network")

    async def aclose(self) -> None:
        pass


async def _ask(http: httpx.AsyncClient, prompt: str) -> str:
    client = AsyncOpenAI(api_key="fake-key", http_client=http)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


@pytest.mark.asyncio
async def test_record_then_replay_non_streaming(tmp_path: Path) -> None:
    """cassette(record) captures a JSON body; cassette(replay) returns it offline."""
    store = FileStore(tmp_path)
    upstream = _CannedJSON(_json_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="record"):
            recorded = await _ask(http, "say hi")
    assert recorded == "Hello world"
    assert upstream.calls == 1

    async with async_client(inner=_NoNetwork()) as http:
        async with cassette(store, mode="replay"):
            replayed = await _ask(http, "say hi")
    assert replayed == "Hello world"


@pytest.mark.asyncio
async def test_auto_records_once_then_replays_non_streaming(tmp_path: Path) -> None:
    """auto mode records the first non-streaming call, replays identical ones."""
    store = FileStore(tmp_path)
    upstream = _CannedJSON(_json_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="auto"):
            first = await _ask(http, "say hi")
            second = await _ask(http, "say hi")

    assert first == second == "Hello world"
    assert upstream.calls == 1, "second identical call should replay, not re-record"
    assert len(store) == 1


@pytest.mark.asyncio
async def test_auto_keying_distinguishes_prompts_non_streaming(tmp_path: Path) -> None:
    """Different prompts produce separate cassettes; identical ones share one."""
    store = FileStore(tmp_path)
    upstream = _CannedJSON(_json_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="auto"):
            await _ask(http, "prompt A")
            await _ask(http, "prompt B")
            await _ask(http, "prompt A")  # repeat — no new cassette

    assert upstream.calls == 2
    assert len(store) == 2


@pytest.mark.asyncio
async def test_non_streaming_captures_provenance_metadata(tmp_path: Path) -> None:
    """A non-streaming recording carries the same corpus provenance as a streaming one."""
    store = FileStore(tmp_path)
    upstream = _CannedJSON(_json_body("Hello world"))

    async with async_client(inner=upstream) as http:
        async with cassette(store, mode="record", id="probe"):
            await _ask(http, "say hi")

    interaction = await store.load("probe")
    meta = interaction.metadata
    assert meta["provider"] == "openai"
    assert meta["model"] == "gpt-4o-mini"
    assert meta["semantic_key"] and isinstance(meta["semantic_key"], str)
    assert "recorded_at" in meta
