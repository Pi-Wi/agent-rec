"""
Acceptance tests for the streaming record/replay mechanic.

test_replay_offline
    Fully offline.  Feeds hardcoded OpenAI-shaped SSE bytes through
    ReplayTransport and asserts the SDK reassembles the correct tool call.
    Also asserts that no real network transport is ever invoked.

test_record_and_replay  (skipped when OPENAI_API_KEY is unset)
    End-to-end: record a live streaming response with a tool call, then
    replay from the in-memory store and assert the assembled message is
    identical.  Proves the tee does not break the caller's stream.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple
from unittest import mock

import httpx
import pytest
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk

from agentrec import InMemoryStore, RecordingTransport, ReplayTransport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Return current weather for a location.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
]

MESSAGES = [{"role": "user", "content": "What's the weather like in Paris?"}]


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


# Minimal but realistic OpenAI SSE stream that calls get_weather("Paris").
# Chunk boundaries mirror what the API actually emits: first chunk carries
# the tool call scaffold (id + name), subsequent chunks carry argument tokens.
_FAKE_SSE_CHUNKS: List[bytes] = [
    _sse(
        {
            "id": "chatcmpl-test123",
            "object": "chat.completion.chunk",
            "created": 1_700_000_000,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_abc",
                                "type": "function",
                                "function": {"name": "get_weather", "arguments": ""},
                            }
                        ],
                    },
                    "finish_reason": None,
                }
            ],
        }
    ),
    _sse(
        {
            "id": "chatcmpl-test123",
            "object": "chat.completion.chunk",
            "created": 1_700_000_000,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"arguments": '{"loc'}}]
                    },
                    "finish_reason": None,
                }
            ],
        }
    ),
    _sse(
        {
            "id": "chatcmpl-test123",
            "object": "chat.completion.chunk",
            "created": 1_700_000_000,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": 'ation": "Paris"}'}}
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
    ),
    _sse(
        {
            "id": "chatcmpl-test123",
            "object": "chat.completion.chunk",
            "created": 1_700_000_000,
            "model": "gpt-4o-mini",
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": "tool_calls"}
            ],
        }
    ),
    b"data: [DONE]\n\n",
]

_FAKE_RESPONSE_HEADERS: List[Tuple[bytes, bytes]] = [
    (b"content-type", b"text/event-stream; charset=utf-8"),
    (b"cache-control", b"no-cache"),
    (b"transfer-encoding", b"chunked"),
]


async def _collect(stream) -> Dict:
    """Drain an OpenAI AsyncStream and accumulate content + tool calls."""
    content = ""
    tool_calls: Dict[int, Dict] = {}

    async for chunk in stream:
        chunk: ChatCompletionChunk
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            content += delta.content
        if delta.tool_calls:
            for tc in delta.tool_calls:
                entry = tool_calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    entry["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        entry["name"] += tc.function.name
                    if tc.function.arguments:
                        entry["arguments"] += tc.function.arguments

    return {"content": content, "tool_calls": list(tool_calls.values())}


# ---------------------------------------------------------------------------
# Test 1: fully offline replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_offline() -> None:
    """
    Replay hardcoded SSE bytes through ReplayTransport and assert:
      1. The OpenAI SDK reassembles the correct tool call (name + arguments).
      2. No real httpx.AsyncHTTPTransport was ever consulted.
    """
    store = InMemoryStore()
    iid = "offline_tool_call"

    # Manually seed the store with the fake SSE frames.
    from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest

    interaction = CapturedInteraction(
        request=CapturedRequest(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers=[],
            content=b"",
        ),
        response_status=200,
        response_headers=_FAKE_RESPONSE_HEADERS,
        response_extensions={},
        chunks=[CapturedChunk(data=b, timestamp_offset=i * 0.01) for i, b in enumerate(_FAKE_SSE_CHUNKS)],
    )
    await store.save(iid, interaction)

    # Patch the real transport so any accidental network call fails loudly.
    with mock.patch.object(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        side_effect=AssertionError("ReplayTransport must not touch the network"),
    ):
        transport = ReplayTransport(store=store, interaction_id=iid)
        http_client = httpx.AsyncClient(transport=transport, base_url="https://api.openai.com")
        async with http_client:
            client = AsyncOpenAI(api_key="fake-key", http_client=http_client)
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=MESSAGES,
                tools=TOOLS,
                stream=True,
            )
            result = await _collect(stream)

    assert result["tool_calls"], "Expected at least one tool call in the replayed response"
    tc = result["tool_calls"][0]
    assert tc["name"] == "get_weather", f"Unexpected tool name: {tc['name']!r}"
    assert json.loads(tc["arguments"]) == {"location": "Paris"}, (
        f"Unexpected tool arguments: {tc['arguments']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: live record → replay (requires OPENAI_API_KEY)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping live record/replay test",
)
async def test_record_and_replay() -> None:
    """
    Record a real OpenAI streaming response, then replay it offline and
    assert that the assembled message (content + tool call name + arguments)
    is bit-for-bit identical.

    The replay phase uses a patched httpx.AsyncHTTPTransport that raises on
    any real connection attempt, proving the replay is fully offline.
    """
    store = InMemoryStore()
    iid = "live_tool_call"

    # ------------------------------------------------------------------
    # Record phase: real network call through RecordingTransport.
    # ------------------------------------------------------------------
    inner = httpx.AsyncHTTPTransport()
    record_transport = RecordingTransport(inner=inner, store=store, interaction_id=iid)

    async with httpx.AsyncClient(transport=record_transport) as http_client:
        client = AsyncOpenAI(http_client=http_client)
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=MESSAGES,
            tools=TOOLS,
            stream=True,
        )
        recorded = await _collect(stream)

    # Sanity-check: the live call produced a tool call.
    assert recorded["tool_calls"], "Live API did not return a tool call — adjust the prompt/model"

    # ------------------------------------------------------------------
    # Replay phase: offline, no network allowed.
    # ------------------------------------------------------------------
    assert iid in store, "RecordingTransport did not persist the interaction"

    with mock.patch.object(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        side_effect=AssertionError("ReplayTransport must not touch the network"),
    ):
        replay_transport = ReplayTransport(store=store, interaction_id=iid)
        async with httpx.AsyncClient(transport=replay_transport) as http_client:
            client = AsyncOpenAI(http_client=http_client)
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=MESSAGES,
                tools=TOOLS,
                stream=True,
            )
            replayed = await _collect(stream)

    # ------------------------------------------------------------------
    # Identity assertion: replay must reconstruct exactly what was recorded.
    # ------------------------------------------------------------------
    assert replayed["content"] == recorded["content"], (
        "Content mismatch between record and replay"
    )
    assert len(replayed["tool_calls"]) == len(recorded["tool_calls"]), (
        "Tool-call count mismatch between record and replay"
    )
    for r_tc, p_tc in zip(recorded["tool_calls"], replayed["tool_calls"]):
        assert p_tc["name"] == r_tc["name"], (
            f"Tool name mismatch: recorded={r_tc['name']!r}, replayed={p_tc['name']!r}"
        )
        # Compare as parsed JSON so whitespace differences don't matter.
        assert json.loads(p_tc["arguments"]) == json.loads(r_tc["arguments"]), (
            f"Tool arguments mismatch:\n  recorded : {r_tc['arguments']}\n  replayed : {p_tc['arguments']}"
        )
