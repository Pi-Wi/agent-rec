"""
Provider-neutrality proof: the same record/replay machinery works against the
Anthropic SDK, with no provider-specific code in agentrec.

test_replay_offline_anthropic
    Fully offline.  Feeds hardcoded Anthropic Messages SSE bytes through
    ReplayTransport and asserts the Anthropic SDK reassembles the text — and
    that no real network transport is ever consulted.

test_record_and_replay_anthropic  (skipped unless ANTHROPIC_API_KEY is set)
    Records a real streaming Anthropic response, then replays it offline and
    asserts the assembled text is identical.
"""
from __future__ import annotations

import os
from typing import List, Tuple
from unittest import mock

import httpx
import pytest

anthropic = pytest.importorskip("anthropic")
from anthropic import AsyncAnthropic  # noqa: E402

from agentrec import InMemoryStore, RecordingTransport, ReplayTransport  # noqa: E402
from agentrec.capture import (  # noqa: E402
    CapturedChunk,
    CapturedInteraction,
    CapturedRequest,
)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is a dev extra; absence just means no .env
    pass

MODEL = "claude-haiku-4-5"


def _event(event_type: str, payload: dict) -> bytes:
    import json

    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n".encode()


# Minimal but valid Anthropic Messages SSE stream emitting "Hello world".
_FAKE_SSE_CHUNKS: List[bytes] = [
    _event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        },
    ),
    _event(
        "content_block_start",
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ),
    _event(
        "content_block_delta",
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}},
    ),
    _event(
        "content_block_delta",
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " world"}},
    ),
    _event("content_block_stop", {"type": "content_block_stop", "index": 0}),
    _event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 2},
        },
    ),
    _event("message_stop", {"type": "message_stop"}),
]

_FAKE_RESPONSE_HEADERS: List[Tuple[bytes, bytes]] = [
    (b"content-type", b"text/event-stream; charset=utf-8"),
    (b"cache-control", b"no-cache"),
]


async def _collect_text(stream) -> str:
    text = ""
    async for event in stream:
        if event.type == "content_block_delta" and event.delta.type == "text_delta":
            text += event.delta.text
    return text


@pytest.mark.asyncio
async def test_replay_offline_anthropic() -> None:
    """Replay hardcoded Anthropic SSE and assert the SDK reassembles the text."""
    store = InMemoryStore()
    iid = "anthropic_offline"

    interaction = CapturedInteraction(
        request=CapturedRequest(
            method="POST",
            url="https://api.anthropic.com/v1/messages",
            headers=[],
            content=b"",
        ),
        response_status=200,
        response_headers=_FAKE_RESPONSE_HEADERS,
        response_extensions={},
        chunks=[CapturedChunk(data=b, timestamp_offset=i * 0.01) for i, b in enumerate(_FAKE_SSE_CHUNKS)],
    )
    await store.save(iid, interaction)

    with mock.patch.object(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        side_effect=AssertionError("ReplayTransport must not touch the network"),
    ):
        transport = ReplayTransport(store=store, key=iid)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = AsyncAnthropic(api_key="fake-key", http_client=http_client)
            stream = await client.messages.create(
                model=MODEL,
                max_tokens=64,
                messages=[{"role": "user", "content": "say hi"}],
                stream=True,
            )
            text = await _collect_text(stream)

    assert text == "Hello world", f"Unexpected replayed text: {text!r}"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live Anthropic record/replay test",
)
async def test_record_and_replay_anthropic() -> None:
    """Record a real Anthropic streaming response, then replay it offline."""
    store = InMemoryStore()
    iid = "anthropic_live"
    messages = [{"role": "user", "content": "Reply with exactly one word: pong."}]

    inner = httpx.AsyncHTTPTransport()
    record_transport = RecordingTransport(inner=inner, store=store, key=iid)
    async with httpx.AsyncClient(transport=record_transport) as http_client:
        client = AsyncAnthropic(http_client=http_client)
        stream = await client.messages.create(
            model=MODEL, max_tokens=64, messages=messages, stream=True
        )
        recorded = await _collect_text(stream)

    assert recorded.strip(), "Live Anthropic call returned empty text"
    assert iid in store, "RecordingTransport did not persist the interaction"

    with mock.patch.object(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        side_effect=AssertionError("ReplayTransport must not touch the network"),
    ):
        replay_transport = ReplayTransport(store=store, key=iid)
        async with httpx.AsyncClient(transport=replay_transport) as http_client:
            client = AsyncAnthropic(http_client=http_client)
            stream = await client.messages.create(
                model=MODEL, max_tokens=64, messages=messages, stream=True
            )
            replayed = await _collect_text(stream)

    assert replayed == recorded, "Replay text did not match the recorded text"
