"""
httpx transport wrappers for recording and replaying LLM responses (streaming and non-streaming).

RecordingTransport  — pass-through that tees SSE chunks into a store.
ReplayTransport     — offline transport that re-emits stored chunks in order.
AutoTransport       — per request: replay if a recording exists, else record.

Sync variants (``SyncRecordingTransport`` / ``SyncReplayTransport`` /
``SyncAutoTransport``) mirror the async ones for SDKs built on ``httpx.Client``.
They require a store implementing the sync store interface (both built-in
stores do).

Design notes
------------
* We capture raw bytes at the transport layer, deliberately below any SDK
  parsing.  This keeps the capture logic provider-neutral (OpenAI SSE and
  Anthropic SSE look identical here — both are byte streams).
* The tee never buffers the full response before yielding to the caller.
  Chunks flow to the caller AND to the store concurrently, one at a time.
  (The *recorder* does hold all chunks in memory until the stream ends —
  the store write is a single commit — so a pathologically large response
  costs its full size in memory once.)
* on_done() fires in the finally-block of the async generator so it runs
  whether the stream is exhausted normally or abandoned (break / exception).
  _TeeStream.aclose() then closes the underlying source; the _done flag
  prevents double-finalisation.
* Error responses (status >= 400) are NOT recorded by default: a cached 429
  or 500 would be replayed forever in auto mode, masking later successes.
  Pass ``record_errors=True`` to capture them deliberately (e.g. to test an
  SDK's error handling against a recorded 4xx).

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
from typing import AsyncIterator, Callable, Coroutine, Dict, Iterator, List, Optional, Union

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


def _is_recordable(status_code: int) -> bool:
    """Whether a response status is worth persisting (2xx/3xx)."""
    return 200 <= status_code < 400


def _build_interaction(
    request: httpx.Request,
    response_status: int,
    response_headers,
    response_extensions: Optional[dict],
    extra_metadata: ExtraMetadata,
) -> CapturedInteraction:
    """Capture request + response envelope; shared by both recording transports."""
    # Fingerprint once: provenance for the corpus (provider, model,
    # semantic_key) so a later migration report can group the same logical
    # call across models without re-parsing every body.
    fp = fingerprint(request)
    interaction = CapturedInteraction(
        request=CapturedRequest(
            method=request.method,
            url=str(request.url),
            headers=list(request.headers.raw),
            content=request.content,
        ),
        response_status=response_status,
        response_headers=list(response_headers.raw),
        response_extensions={
            k: v for k, v in (response_extensions or {}).items() if k not in _EPHEMERAL_EXTENSIONS
        },
        metadata=fp.as_metadata(),
    )
    if extra_metadata is not None:
        extra = extra_metadata(request) if callable(extra_metadata) else extra_metadata
        interaction.metadata.update(extra)
    return interaction


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
        self._source_closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._source:
                await self._on_chunk(chunk, time.monotonic() - self._start)
                yield chunk
        finally:
            await self._finalize()

    async def aclose(self) -> None:
        # Guarded: httpx calls aclose() after iteration too, and not every
        # inner stream tolerates a double close.
        if not self._source_closed:
            self._source_closed = True
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

    Error responses (status >= 400) pass through unrecorded unless
    ``record_errors=True`` — a cached failure would otherwise be replayed
    forever in auto mode.
    """

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        store: InteractionStore,
        key: KeyLike = None,
        extra_metadata: ExtraMetadata = None,
        record_errors: bool = False,
    ) -> None:
        self._inner = inner
        self._store = store
        self._keyer = _as_keyer(key)
        self._extra_metadata = extra_metadata
        self._record_errors = record_errors

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Ensure the request body is buffered so the inner transport can read it
        # even after we peek at it.  aread() caches to request._content and
        # resets request.stream to a replayable ByteStream.
        await request.aread()
        interaction_id = self._keyer(request)

        start = time.monotonic()
        response = await self._inner.handle_async_request(request)
        if not self._record_errors and not _is_recordable(response.status_code):
            return response  # pass the failure through untouched, never cache it

        interaction = _build_interaction(
            request,
            response.status_code,
            response.headers,
            response.extensions,
            self._extra_metadata,
        )

        async def on_chunk(data: bytes, offset: float) -> None:
            if not interaction.chunks:
                interaction.metadata["latency_first_chunk_s"] = round(
                    time.monotonic() - start, 4
                )
            interaction.chunks.append(CapturedChunk(data=data, timestamp_offset=offset))

        async def on_done() -> None:
            # Request sent → response stream finished.  Provenance, like
            # recorded_at: lets a migration report put real numbers on the
            # latency question (best-effort; an abandoned stream records the
            # time until abandonment).
            interaction.metadata["latency_s"] = round(time.monotonic() - start, 4)
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
        record_errors: bool = False,
    ) -> None:
        self._store = store
        self._keyer = _as_keyer(key)
        self._record = RecordingTransport(inner, store, self._keyer, extra_metadata, record_errors)
        self._replay = ReplayTransport(store, self._keyer, simulate_timing)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        if await self._store.has(self._keyer(request)):
            return await self._replay.handle_async_request(request)
        return await self._record.handle_async_request(request)

    async def aclose(self) -> None:
        await self._record.aclose()


# ---------------------------------------------------------------------------
# Sync mirrors — same behaviour, for SDKs built on httpx.Client
# ---------------------------------------------------------------------------


class _SyncTeeStream(httpx.SyncByteStream):
    """Sync twin of :class:`_TeeStream`; see that class for the contract."""

    def __init__(
        self,
        source: httpx.SyncByteStream,
        on_chunk: Callable[[bytes, float], None],
        on_done: Callable[[], None],
    ) -> None:
        self._source = source
        self._on_chunk = on_chunk
        self._on_done = on_done
        self._start = time.monotonic()
        self._done = False
        self._source_closed = False

    def __iter__(self) -> Iterator[bytes]:
        try:
            for chunk in self._source:
                self._on_chunk(chunk, time.monotonic() - self._start)
                yield chunk
        finally:
            self._finalize()

    def close(self) -> None:
        if not self._source_closed:
            self._source_closed = True
            self._source.close()
        self._finalize()

    def _finalize(self) -> None:
        if not self._done:
            self._done = True
            self._on_done()


class _SyncReplayStream(httpx.SyncByteStream):
    """Sync twin of :class:`_ReplayStream`."""

    def __init__(self, chunks: List[CapturedChunk], simulate_timing: bool = False) -> None:
        self._chunks = chunks
        self._simulate_timing = simulate_timing

    def __iter__(self) -> Iterator[bytes]:
        last = 0.0
        for chunk in self._chunks:
            if self._simulate_timing:
                delay = chunk.timestamp_offset - last
                if delay > 0:
                    time.sleep(delay)
                last = chunk.timestamp_offset
            yield chunk.data

    def close(self) -> None:
        pass


def _sync_replay_response(interaction: CapturedInteraction, simulate_timing: bool) -> httpx.Response:
    return httpx.Response(
        status_code=interaction.response_status,
        headers=interaction.response_headers,
        stream=_SyncReplayStream(interaction.chunks, simulate_timing),
        extensions=interaction.response_extensions,
    )


class SyncRecordingTransport(httpx.BaseTransport):
    """Sync twin of :class:`RecordingTransport`.

    Requires a store implementing the sync store interface
    (:meth:`~agentrec.store.InteractionStore.save_sync` etc.); both built-in
    stores do.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport,
        store: InteractionStore,
        key: KeyLike = None,
        extra_metadata: ExtraMetadata = None,
        record_errors: bool = False,
    ) -> None:
        self._inner = inner
        self._store = store
        self._keyer = _as_keyer(key)
        self._extra_metadata = extra_metadata
        self._record_errors = record_errors

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.read()  # buffer the body so we can fingerprint it and still send it
        interaction_id = self._keyer(request)

        start = time.monotonic()
        response = self._inner.handle_request(request)
        if not self._record_errors and not _is_recordable(response.status_code):
            return response

        interaction = _build_interaction(
            request,
            response.status_code,
            response.headers,
            response.extensions,
            self._extra_metadata,
        )

        def on_chunk(data: bytes, offset: float) -> None:
            if not interaction.chunks:
                interaction.metadata["latency_first_chunk_s"] = round(
                    time.monotonic() - start, 4
                )
            interaction.chunks.append(CapturedChunk(data=data, timestamp_offset=offset))

        def on_done() -> None:
            interaction.metadata["latency_s"] = round(time.monotonic() - start, 4)
            interaction.metadata["recorded_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            self._store.save_sync(interaction_id, interaction)

        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_SyncTeeStream(response.stream, on_chunk, on_done),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._inner.close()


class SyncReplayTransport(httpx.BaseTransport):
    """Sync twin of :class:`ReplayTransport` — fully offline, no sockets."""

    def __init__(
        self,
        store: InteractionStore,
        key: KeyLike = None,
        simulate_timing: bool = False,
    ) -> None:
        self._store = store
        self._keyer = _as_keyer(key)
        self._simulate_timing = simulate_timing

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.read()
        interaction = self._store.load_sync(self._keyer(request))
        return _sync_replay_response(interaction, self._simulate_timing)

    def close(self) -> None:
        pass


class SyncAutoTransport(httpx.BaseTransport):
    """Sync twin of :class:`AutoTransport`: replay when recorded, else record."""

    def __init__(
        self,
        inner: httpx.BaseTransport,
        store: InteractionStore,
        key: KeyLike = None,
        simulate_timing: bool = False,
        extra_metadata: ExtraMetadata = None,
        record_errors: bool = False,
    ) -> None:
        self._store = store
        self._keyer = _as_keyer(key)
        self._record = SyncRecordingTransport(inner, store, self._keyer, extra_metadata, record_errors)
        self._replay = SyncReplayTransport(store, self._keyer, simulate_timing)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.read()
        if self._store.has_sync(self._keyer(request)):
            return self._replay.handle_request(request)
        return self._record.handle_request(request)

    def close(self) -> None:
        self._record.close()
