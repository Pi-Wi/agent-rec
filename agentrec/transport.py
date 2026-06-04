"""
httpx transport wrappers for recording and replaying streaming LLM responses.

RecordingTransport  — pass-through that tees SSE chunks into a store.
ReplayTransport     — offline transport that re-emits stored chunks in order.

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
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Callable, Coroutine, List

import httpx

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest
from .store import InteractionStore

# Keys that reference live network objects and cannot be stored.
_EPHEMERAL_EXTENSIONS = frozenset({"network_stream", "trailers"})


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


class RecordingTransport(httpx.AsyncBaseTransport):
    """
    Delegates to *inner* for real network access and tees the streaming
    response into *store* under *interaction_id*.
    """

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        store: InteractionStore,
        interaction_id: str,
    ) -> None:
        self._inner = inner
        self._store = store
        self._interaction_id = interaction_id

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Ensure the request body is buffered so the inner transport can read it
        # even after we peek at it.  aread() caches to request._content and
        # resets request.stream to a replayable ByteStream.
        await request.aread()

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
        )

        async def on_chunk(data: bytes, offset: float) -> None:
            interaction.chunks.append(CapturedChunk(data=data, timestamp_offset=offset))

        async def on_done() -> None:
            await self._store.save(self._interaction_id, interaction)

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

    Raises KeyError (from the store) if no recording exists for interaction_id,
    giving a clear signal that the record phase must run first.
    """

    def __init__(
        self,
        store: InteractionStore,
        interaction_id: str,
        simulate_timing: bool = False,
    ) -> None:
        self._store = store
        self._interaction_id = interaction_id
        self._simulate_timing = simulate_timing

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        interaction = await self._store.load(self._interaction_id)
        return httpx.Response(
            status_code=interaction.response_status,
            headers=interaction.response_headers,
            stream=_ReplayStream(interaction.chunks, self._simulate_timing),
            extensions=interaction.response_extensions,
        )

    async def aclose(self) -> None:
        pass
