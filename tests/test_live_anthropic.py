"""
Live verification of the Anthropic adapter against the real ``/v1/messages`` API.

These drive the exact path the migration runner uses for an Anthropic *target*:
build a request with the adapter, POST it live with a plain httpx client, then
decode the response.  The focus is ``tool_choice`` translation, and in
particular ``{"type": "none"}`` — emitted by the adapter but, until now, never
exercised against the live API (TODO P3).  The two tests are complementary: a
forced choice *must* produce a tool call, and ``none`` *must not* — so a pass
proves the wire spelling is accepted and behaves as intended, not merely that
the request was well-formed.

ANTHROPIC_API_KEY is loaded from the project's .env via python-dotenv; the tests
skip cleanly when no key is available.
"""
from __future__ import annotations

import os

import httpx
import pytest
from dotenv import load_dotenv

from agentrec.providers import Conversation, AnthropicAdapter

# Pull the key out of .env before the skip condition is evaluated (find_dotenv
# walks up to the repo root even though tests live a couple of dirs deeper).
load_dotenv()

# A cheap, current Haiku on /v1/messages.  Override with
# AGENTREC_ANTHROPIC_TEST_MODEL if your key targets a different one.
MODEL = os.getenv("AGENTREC_ANTHROPIC_TEST_MODEL", "claude-haiku-4-5")

_skip = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set (and not in .env) — skipping live Anthropic test",
)

ADAPTER = AnthropicAdapter()

_WEATHER_TOOL = {
    "name": "get_weather",
    "description": "Look up the current weather for a city.",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}


def _weather_conversation(tool_choice) -> Conversation:
    return Conversation(
        messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        max_tokens=256,
        tools=[_WEATHER_TOOL],
        tool_choice=tool_choice,
    )


@_skip
@pytest.mark.asyncio
async def test_live_anthropic_forced_tool_choice_calls() -> None:
    """A forced tool_choice (positive control): the model must emit a call."""
    conversation = _weather_conversation({"name": "get_weather"})
    url, headers, body = ADAPTER.build_request(conversation, MODEL)
    assert body["tool_choice"] == {"type": "tool", "name": "get_weather"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text

    decoded = ADAPTER.decode_response(response.content, is_sse=False)
    assert decoded.tool_calls, "forced tool_choice produced no tool call"
    assert decoded.tool_calls[0].name == "get_weather"


@_skip
@pytest.mark.asyncio
async def test_live_anthropic_tool_choice_none_suppresses_calls() -> None:
    """tool_choice: none — tools are visible but must not be called (TODO P3).

    This is the case the adapter emitted but never verified live: the wire form
    is ``{"type": "none"}``.  Paired with the forced-call test above (same
    prompt and tools), a pass proves the API both *accepts* the spelling and
    *honours* it — identical input that yields a call when forced yields none
    here.

    Note: we assert only that no tool call comes back, not that text does.
    Observed live, Haiku answers this particular prompt with an **empty**
    content array (``stop_reason: end_turn``) — with the weather tool off the
    table it simply has nothing to say.  That is model disposition, not an
    adapter bug (the decoder faithfully reports the empty content), so pinning a
    non-empty answer here would make the test flaky on real behaviour.
    """
    conversation = _weather_conversation("none")
    url, headers, body = ADAPTER.build_request(conversation, MODEL)
    assert body["tool_choice"] == {"type": "none"}  # the spelling under test

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text

    decoded = ADAPTER.decode_response(response.content, is_sse=False)
    assert not decoded.tool_calls, (
        "tool_choice: none should suppress tool calls, but the model called one"
    )
