"""
Live verification of the Mistral adapter against the real
``api.mistral.ai/v1/chat/completions`` endpoint.

Like Gemini, Mistral's SDK does not route through httpx, so there is no recorder
seam to exercise.  These tests drive the exact path the migration runner uses
for a Mistral *target*: build a request with the adapter, POST it live with a
plain httpx client, then decode the response and normalise its usage.  They
cover the three things the connector adds beyond inheriting OpenAI's dialect —
non-streaming, streaming (SSE), and a forced tool call (whose Mistral-specific
"any"/9-char-id handling only matters on the wire) — so passing them is what
would retire the "offline-tested only" caveat in the CHANGELOG.

MISTRAL_API_KEY is loaded from the project's .env via python-dotenv; the tests
skip cleanly when no key is available (the repo's .env ships without one).
"""
from __future__ import annotations

import os

import httpx
import pytest
from dotenv import load_dotenv

from agentrec.providers import Conversation, MistralAdapter

# Pull the key out of .env before the skip condition is evaluated (find_dotenv
# walks up to the repo root even though tests live a couple of dirs deeper).
load_dotenv()

# A cheap, current chat model.  Override with AGENTREC_MISTRAL_TEST_MODEL.
MODEL = os.getenv("AGENTREC_MISTRAL_TEST_MODEL", "mistral-small-latest")

_HAS_KEY = bool(os.getenv("MISTRAL_API_KEY"))
_skip = pytest.mark.skipif(
    not _HAS_KEY,
    reason="MISTRAL_API_KEY not set (and not in .env) — skipping live Mistral test",
)

ADAPTER = MistralAdapter()


@_skip
@pytest.mark.asyncio
async def test_live_mistral_non_streaming() -> None:
    """The migration-target path: build_request -> live POST -> decode + usage."""
    conversation = Conversation(
        messages=[{"role": "user", "content": "Reply with exactly one word: pong."}],
        max_tokens=64,
    )
    url, headers, body = ADAPTER.build_request(conversation, MODEL)
    assert url == "https://api.mistral.ai/v1/chat/completions"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text

    decoded = ADAPTER.decode_response(response.content, is_sse=False)
    assert decoded.text.strip(), "live Mistral returned empty text"
    assert decoded.streamed is False

    usage = ADAPTER.normalize_usage(decoded.usage)
    assert usage.prompt_total and usage.prompt_total > 0
    assert usage.output and usage.output > 0


@_skip
@pytest.mark.asyncio
async def test_live_mistral_streaming_sse() -> None:
    """Decode a real SSE stream (the same endpoint with stream=true in the body)."""
    conversation = Conversation(
        messages=[{"role": "user", "content": "Count to five, one number per line."}],
        max_tokens=64,
    )
    url, headers, body = ADAPTER.build_request(conversation, MODEL)
    body["stream"] = True  # Mistral streams from the same URL, OpenAI-style

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    # The body is a real SSE byte stream; the adapter must join + parse it.
    assert b"data:" in response.content

    decoded = ADAPTER.decode_response(response.content, is_sse=True)
    assert decoded.streamed is True
    assert decoded.text.strip(), "live Mistral stream decoded to empty text"


@_skip
@pytest.mark.asyncio
async def test_live_mistral_tool_call() -> None:
    """A forced tool call round-trips: the model emits a tool_call we decode."""
    conversation = Conversation(
        messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        max_tokens=128,
        tools=[
            {
                "name": "get_weather",
                "description": "Look up the current weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ],
        tool_choice={"name": "get_weather"},  # force it, so the test is deterministic
    )
    url, headers, body = ADAPTER.build_request(conversation, MODEL)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text

    decoded = ADAPTER.decode_response(response.content, is_sse=False)
    assert decoded.tool_calls, "forced tool_choice did not produce a tool call"
    call = decoded.tool_calls[0]
    assert call.name == "get_weather"
    assert isinstance(call.arguments, dict)  # args decoded as a JSON object
