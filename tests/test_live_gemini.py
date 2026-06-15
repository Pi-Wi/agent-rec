"""
Live verification of the Gemini adapter against the real ``generateContent`` API.

The Gemini SDK does not route through httpx, so there is no recorder seam to
exercise (unlike ``test_live_record.py``).  Instead these tests drive the exact
path the migration runner uses for a Gemini *target*: build a request with the
adapter, POST it live with a plain httpx client, then decode the response and
normalise its usage.  They cover the three things the 0.8.0 CHANGELOG flagged
as not-yet-live-verified — non-streaming, streaming (SSE), and tool calls — so
passing them is what retires that caveat.

GEMINI_API_KEY (or GOOGLE_API_KEY) is loaded from the project's .env via
python-dotenv; the tests skip cleanly when no key is available.
"""
from __future__ import annotations

import os

import httpx
import pytest
from dotenv import load_dotenv

from agentrec.providers import Conversation, GeminiAdapter

# Pull the key out of .env before the skip condition is evaluated (find_dotenv
# walks up to the repo root even though tests live a couple of dirs deeper).
load_dotenv()

# A cheap, current flash model on the v1beta generateContent endpoint.  Override
# with AGENTREC_GEMINI_TEST_MODEL if your key targets a different one.  Note
# 2.5-flash is a *thinking* model: a tiny max_tokens can be spent on reasoning
# with nothing left for visible text, so these tests give it real headroom (the
# migration runner defaults to --max-tokens 4096, so this matches real use).
MODEL = os.getenv("AGENTREC_GEMINI_TEST_MODEL", "gemini-2.5-flash")

_HAS_KEY = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
_skip = pytest.mark.skipif(
    not _HAS_KEY,
    reason="GEMINI_API_KEY/GOOGLE_API_KEY not set (and not in .env) — skipping live Gemini test",
)

ADAPTER = GeminiAdapter()


@_skip
@pytest.mark.asyncio
async def test_live_gemini_non_streaming() -> None:
    """The migration-target path: build_request -> live POST -> decode + usage."""
    conversation = Conversation(
        messages=[{"role": "user", "content": "Reply with exactly one word: pong."}],
        max_tokens=512,
    )
    url, headers, body = ADAPTER.build_request(conversation, MODEL)
    assert url.endswith(":generateContent")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text

    decoded = ADAPTER.decode_response(response.content, is_sse=False)
    assert decoded.text.strip(), "live Gemini returned empty text"
    assert decoded.streamed is False

    usage = ADAPTER.normalize_usage(decoded.usage)
    assert usage.prompt_total and usage.prompt_total > 0
    assert usage.output and usage.output > 0


@_skip
@pytest.mark.asyncio
async def test_live_gemini_streaming_sse() -> None:
    """Decode a real SSE stream (streamGenerateContent?alt=sse)."""
    conversation = Conversation(
        messages=[{"role": "user", "content": "Count to five, one number per line."}],
        max_tokens=512,
    )
    url, headers, body = ADAPTER.build_request(conversation, MODEL)
    stream_url = url.replace(":generateContent", ":streamGenerateContent") + "?alt=sse"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(stream_url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    # The body is a real SSE byte stream; the adapter must join + parse it.
    assert b"data:" in response.content

    decoded = ADAPTER.decode_response(response.content, is_sse=True)
    assert decoded.streamed is True
    assert decoded.text.strip(), "live Gemini stream decoded to empty text"


@_skip
@pytest.mark.asyncio
async def test_live_gemini_tool_call() -> None:
    """A forced tool call round-trips: the model emits a functionCall we decode."""
    conversation = Conversation(
        messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        max_tokens=512,
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
