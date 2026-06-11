"""
Offline tests for FileStore — persistence and replay round-trip.

No network or API key required.  We seed an interaction with hardcoded SSE
frames, persist it to a temp directory, reload it in a *fresh* store (proving
it came off disk, not memory), and replay it through the OpenAI SDK.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

from agentrec import FileStore, ReplayTransport
from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


_CHUNKS = [
    _sse(
        {
            "id": "chatcmpl-x",
            "object": "chat.completion.chunk",
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hello"}}],
        }
    ),
    _sse(
        {
            "id": "chatcmpl-x",
            "object": "chat.completion.chunk",
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {"content": " world"}}],
        }
    ),
    _sse(
        {
            "id": "chatcmpl-x",
            "object": "chat.completion.chunk",
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    ),
    b"data: [DONE]\n\n",
]


def _make_interaction() -> CapturedInteraction:
    return CapturedInteraction(
        request=CapturedRequest(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            # Includes a secret that FileStore must redact on save.
            headers=[(b"authorization", b"Bearer sk-supersecret")],
            content=b'{"model":"gpt-4o-mini"}',
        ),
        response_status=200,
        response_headers=[(b"content-type", b"text/event-stream; charset=utf-8")],
        response_extensions={"http_version": b"HTTP/1.1", "reason_phrase": b"OK"},
        chunks=[CapturedChunk(data=b, timestamp_offset=i * 0.01) for i, b in enumerate(_CHUNKS)],
    )


@pytest.mark.asyncio
async def test_filestore_roundtrip(tmp_path: Path) -> None:
    """save() writes a file; a fresh load() reconstructs the interaction exactly."""
    store = FileStore(tmp_path)
    iid = "hello_world"

    assert iid not in store
    await store.save(iid, _make_interaction())

    # A real file landed on disk and the store reports the corpus size.
    assert (tmp_path / "hello_world.json").exists()
    assert iid in store
    assert len(store) == 1
    assert store.ids() == ["hello_world"]

    # Reload through a brand-new store object — guarantees it comes off disk.
    reloaded = await FileStore(tmp_path).load(iid)
    assert reloaded.response_status == 200
    assert [c.data for c in reloaded.chunks] == _CHUNKS
    assert reloaded.response_extensions["http_version"] == b"HTTP/1.1"


@pytest.mark.asyncio
async def test_filestore_redacts_authorization(tmp_path: Path) -> None:
    """The API key must never be written to the on-disk cassette."""
    store = FileStore(tmp_path)
    await store.save("secret", _make_interaction())

    raw = (tmp_path / "secret.json").read_text(encoding="utf-8")
    assert "sk-supersecret" not in raw
    assert "supersecret" not in raw

    reloaded = await store.load("secret")
    assert reloaded.request.headers[0] == (b"authorization", b"[REDACTED]")


@pytest.mark.asyncio
async def test_filestore_redacts_response_set_cookie(tmp_path: Path) -> None:
    """Response Set-Cookie values (e.g. CDN session cookies) never hit disk."""
    interaction = _make_interaction()
    interaction.response_headers.append(
        (b"set-cookie", b"__cf_bm=secret-cookie-value; path=/; HttpOnly")
    )
    store = FileStore(tmp_path)
    await store.save("cookie", interaction)

    raw = (tmp_path / "cookie.json").read_text(encoding="utf-8")
    assert "secret-cookie-value" not in raw

    reloaded = await store.load("cookie")
    assert (b"set-cookie", b"[REDACTED]") in reloaded.response_headers


@pytest.mark.asyncio
async def test_filestore_sanitizes_hostile_interaction_ids(tmp_path: Path) -> None:
    """Ids with separators/colons map to a file inside the corpus directory."""
    root = tmp_path / "corpus"
    store = FileStore(root)
    hostile = "..\\..\\C:evil/id"

    await store.save(hostile, _make_interaction())

    files = list(root.glob("*.json"))
    assert len(files) == 1, "the cassette must land inside the corpus root"
    assert await store.has(hostile)
    assert (await store.load(hostile)).response_status == 200
    await store.discard(hostile)
    assert not await store.has(hostile)


@pytest.mark.asyncio
async def test_filestore_is_human_readable(tmp_path: Path) -> None:
    """SSE content is stored as plain text, not base64, so a cassette is legible."""
    store = FileStore(tmp_path)
    await store.save("readable", _make_interaction())

    raw = (tmp_path / "readable.json").read_text(encoding="utf-8")
    # The actual SSE frames and their content are visible verbatim in the file.
    assert "chat.completion.chunk" in raw
    assert "Hello" in raw and "world" in raw
    assert "data: [DONE]" in raw
    # Readable header text, not base64 blobs.
    assert "text/event-stream" in raw


@pytest.mark.asyncio
async def test_filestore_scrubs_request_body_secret(tmp_path: Path) -> None:
    """A secret pasted into the request body is redacted before it hits disk."""
    body = json.dumps(
        {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "use my key sk-abcdEFGH1234567890zzzz"},
                {"role": "user", "content": '{"password": "hunter2"}'},
            ],
        }
    ).encode()
    interaction = _make_interaction()
    interaction.request.content = body

    store = FileStore(tmp_path)  # scrubbing on by default
    await store.save("with_secret", interaction)

    raw = (tmp_path / "with_secret.json").read_text(encoding="utf-8")
    assert "sk-abcdEFGH1234567890zzzz" not in raw
    assert "hunter2" not in raw
    assert "[REDACTED-OPENAI-KEY]" in raw

    reloaded = await store.load("with_secret")
    assert b"sk-abcdEFGH1234567890zzzz" not in reloaded.request.content
    assert b"hunter2" not in reloaded.request.content


@pytest.mark.asyncio
async def test_filestore_scrub_can_be_disabled(tmp_path: Path) -> None:
    """Opt-out keeps the request body verbatim for callers who need it."""
    interaction = _make_interaction()
    interaction.request.content = b'{"note": "sk-abcdEFGH1234567890zzzz"}'

    store = FileStore(tmp_path, scrub_request_body=False)
    await store.save("verbatim", interaction)

    reloaded = await store.load("verbatim")
    assert b"sk-abcdEFGH1234567890zzzz" in reloaded.request.content


@pytest.mark.asyncio
async def test_filestore_replays_through_sdk(tmp_path: Path) -> None:
    """A persisted interaction replays offline and the SDK reassembles it."""
    store = FileStore(tmp_path)
    iid = "replayed"
    await store.save(iid, _make_interaction())

    transport = ReplayTransport(store=store, key=iid)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.openai.com") as http_client:
        client = AsyncOpenAI(api_key="fake-key", http_client=http_client)
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        content = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content

    assert content == "Hello world"
