"""
Live recording test against the actual OpenAI API.

Makes a genuine streaming chat-completion call through RecordingTransport and
asserts that the interaction is captured into the store: the SDK reassembles a
real assistant response and the raw SSE chunks are persisted for later replay.

The OPENAI_API_KEY is loaded from the project's .env via python-dotenv, so the
test runs as soon as that file is present — no need to export the variable by
hand.  When no key is available the test skips rather than failing.
"""
from __future__ import annotations

import os

import httpx
import pytest
from dotenv import load_dotenv
from openai import AsyncOpenAI

from agentrec import InMemoryStore, RecordingTransport

# Pull OPENAI_API_KEY out of .env before the skip condition below is evaluated.
# find_dotenv() walks up from this file, so it locates the repo-root .env even
# though the tests live a couple of directories deeper.
load_dotenv()

MESSAGES = [{"role": "user", "content": "Reply with exactly one word: pong."}]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set (and not found in .env) — skipping live record test",
)
async def test_live_record(model: str = "gpt-4o-mini") -> None:
    """Record a real streaming OpenAI response and assert it was captured."""
    store = InMemoryStore()
    iid = "live_record"

    inner = httpx.AsyncHTTPTransport()
    record_transport = RecordingTransport(inner=inner, store=store, key=iid)

    content = ""
    async with httpx.AsyncClient(transport=record_transport) as http_client:
        client = AsyncOpenAI(http_client=http_client)
        stream = await client.chat.completions.create(
            model=model,
            messages=MESSAGES,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content

    # The live call produced a non-empty assistant message.
    assert content.strip(), "Live API returned an empty response"

    # The tee persisted the interaction with its raw SSE chunks intact.
    assert iid in store, "RecordingTransport did not persist the interaction"
    interaction = await store.load(iid)
    assert interaction.response_status == 200
    assert interaction.chunks, "No SSE chunks were captured during recording"
    assert any(b"chat.completion.chunk" in c.data for c in interaction.chunks), (
        "Captured chunks do not look like an OpenAI SSE stream"
    )
