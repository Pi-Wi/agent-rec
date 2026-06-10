"""
httpx transport wrappers for recording and replaying LLM responses (streaming and non-streaming).

RecordingTransport  — pass-through that tees SSE chunks into a store.
ReplayTransport     — offline transport that re-emits stored chunks in order.
AutoTransport       — per request: replay if a recording exists, else record.

Design notes
------------
* We capture raw bytes at the transport layer, deliberately below any SDK
  parsing.  This keeps the capture logic provider-neutral (OpenAI SSE and
  Anthropic SSE look identical here — both are byte streams).
* The tee never buffers the full response before yielding to the caller.
  Chunks flow to the caller AND to the store concurrently, one at a time.
* on_done() fires in the finally-block of the async generator so it runs
  whether the stream is exhausted normally or abandoned (break / exception).
  _TeeStream.aclose() then closes the underlying source; the _done flag
  prevents double-finalisation.

Keying
------
Each transport takes a ``key`` that resolves an interaction id from the
request.  Pass a string for a fixed id (one cassette), or a callable for
per-request keying.  The default (``key=None``) derives a stable id from the
request fingerprint, so a single transport handles many distinct calls and the
same call replays deterministically — see :mod:`agentrec.keying`.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import time
from typing import AsyncIterator, Callable, Coroutine, Dict, List, Optional, Union

import httpx

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest
from .keying import default_key, fingerprint
from .store import InteractionStore

# Keys that reference live network objects and cannot be stored.
_EPHEMERAL_EXTENSIONS = frozenset({"network_stream", "trailers"})

# A key is either a fixed interaction id or a function of the request.
Keyer = Callable[[httpx.Request], str]
KeyLike = Union[str, Keyer, None]

# Extra metadata merged into a recorded interaction after fingerprint stamping.
# A dict applies to every request; a callable derives it per request.  Used by
# the migration runner to pin the baseline's semantic_key and record lineage
# (``migrated_from``) on cross-model cassettes.
ExtraMetadata = Union[Dict[str, object], Callable[[httpx.Request], Dict[str, object]], None]


def _as_keyer(key: KeyLike) -> Keyer:
    """Normalise ``key`` to a ``request -> id`` callable."""
    if key is None:
        return default_key
    if callable(key):
        return key
    fixed = key
    return lambda _request: fixed


class _TeeStream(httpx.AsyncByteStream):
    """
    Wraps a real network byte stream.  Each chunk is forwarded to the caller
    AND to on_chunk().  When the generator exits (exhausted or abandoned),
    on_done() is called exactly once to commit the recorded interaction.
    """

    def __init__(
        self,
        source: httpx.AsyncByteStream,
        on_chunk: Callable[[bytes, float], Coroutine],
        on_done: Callable[[], Coroutine],
    ) -> None:
        self._source = source
        self._on_chunk = on_chunk
        self._on_done = on_done
        self._start = time.monotonic()
        self._done = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._source:
                await self._on_chunk(chunk, time.monotonic() - self._start)
                yield chunk
        finally:
            await self._finalize()

    async def aclose(self) -> None:
        await self._source.aclose()
        await self._finalize()

    async def _finalize(self) -> None:
        if not self._done:
            self._done = True
            await self._on_done()


class _ReplayStream(httpx.AsyncByteStream):
    """
    Re-emits stored chunks in the original order.
    simulate_timing=True reproduces the original inter-chunk delays.
    """

    def __init__(
        self,
        chunks: List[CapturedChunk],
        simulate_timing: bool = False,
    ) -> None:
        self._chunks = chunks
        self._simulate_timing = simulate_timing

    async def __aiter__(self) -> AsyncIterator[bytes]:
        last = 0.0
        for chunk in self._chunks:
            if self._simulate_timing:
                delay = chunk.timestamp_offset - last
                if delay > 0:
                    await asyncio.sleep(delay)
                last = chunk.timestamp_offset
            yield chunk.data

    async def aclose(self) -> None:
        pass


def _replay_response(interaction: CapturedInteraction, simulate_timing: bool) -> httpx.Response:
    return httpx.Response(
        status_code=interaction.response_status,
        headers=interaction.response_headers,
        stream=_ReplayStream(interaction.chunks, simulate_timing),
        extensions=interaction.response_extensions,
    )


class RecordingTransport(httpx.AsyncBaseTransport):
    """
    Delegates to *inner* for real network access and tees the streaming
    response into *store* under the resolved key.
    """

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        store: InteractionStore,
        key: KeyLike = None,
        extra_metadata: ExtraMetadata = None,
    ) -> None:
        self._inner = inner
        self._store = store
        self._keyer = _as_keyer(key)
        self._extra_metadata = extra_metadata

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Ensure the request body is buffered so the inner transport can read it
        # even after we peek at it.  aread() caches to request._content and
        # resets request.stream to a replayable ByteStream.
        await request.aread()

        interaction_id = self._keyer(request)
        # Fingerprint the request once: provenance for the corpus (provider,
        # model, semantic_key) so a later migration report can group the same
        # logical call across models without re-parsing every body.
        fp = fingerprint(request)

        captured_req = CapturedRequest(
            method=request.method,
            url=str(request.url),
            headers=list(request.headers.raw),
            content=request.content,
        )

        response = await self._inner.handle_async_request(request)

        interaction = CapturedInteraction(
            request=captured_req,
            response_status=response.status_code,
            response_headers=list(response.headers.raw),
            response_extensions={
                k: v
                for k, v in (response.extensions or {}).items()
                if k not in _EPHEMERAL_EXTENSIONS
            },
            metadata=fp.as_metadata(),
        )
        if self._extra_metadata is not None:
            extra = (
                self._extra_metadata(request)
                if callable(self._extra_metadata)
                else self._extra_metadata
            )
            interaction.metadata.update(extra)

        async def on_chunk(data: bytes, offset: float) -> None:
            interaction.chunks.append(CapturedChunk(data=data, timestamp_offset=offset))

        async def on_done() -> None:
            interaction.metadata["recorded_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            await self._store.save(interaction_id, interaction)

        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_TeeStream(response.stream, on_chunk, on_done),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


class ReplayTransport(httpx.AsyncBaseTransport):
    """
    Fully offline transport.  Every request is answered from the store;
    no sockets are opened.

    Raises KeyError (from the store) if no recording exists for the resolved
    key, giving a clear signal that the record phase must run first.
    """

    def __init__(
        self,
        store: InteractionStore,
        key: KeyLike = None,
        simulate_timing: bool = False,
    ) -> None:
        self._store = store
        self._keyer = _as_keyer(key)
        self._simulate_timing = simulate_timing

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Read the body so the keyer can fingerprint it (no-op for a fixed key).
        await request.aread()
        interaction = await self._store.load(self._keyer(request))
        return _replay_response(interaction, self._simulate_timing)

    async def aclose(self) -> None:
        pass


class AutoTransport(httpx.AsyncBaseTransport):
    """
    Cassette semantics: replay when a recording exists for the request, else
    record it through *inner*.  With the default keyer this gives true
    record-once / replay-thereafter behaviour keyed on the request itself.
    """

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        store: InteractionStore,
        key: KeyLike = None,
        simulate_timing: bool = False,
        extra_metadata: ExtraMetadata = None,
    ) -> None:
        self._store = store
        self._keyer = _as_keyer(key)
        self._record = RecordingTransport(inner, store, self._keyer, extra_metadata)
        self._replay = ReplayTransport(store, self._keyer, simulate_timing)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        if await self._store.has(self._keyer(request)):
            return await self._replay.handle_async_request(request)
        return await self._record.handle_async_request(request)

    async def aclose(self) -> None:
        await self._record.aclose()
