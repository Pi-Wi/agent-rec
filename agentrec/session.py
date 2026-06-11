"""
High-level, ergonomic entry points over the low-level transports.

The transports interception point is the httpx client *inside* an SDK
(``AsyncOpenAI(http_client=...)``, ``AsyncAnthropic(http_client=...)``).  This
module gives you one client to build and a scope to wrap your calls in:

    http = agentrec.async_client()
    oai = AsyncOpenAI(http_client=http)

    @agentrec.cassette(store, mode="auto")        # decorator
    async def ask(prompt):
        return await oai.chat.completions.create(...)

    async with agentrec.cassette(store, mode="record"):   # or context manager
        await oai.chat.completions.create(...)

``async_client`` returns an httpx client whose transport consults a contextvar
on every request: inside an active ``cassette`` scope it records / replays /
auto-resolves; outside any scope it passes straight through to the network.
One client, many independently-scoped cassettes — the shape a test suite wants.

Provider-neutral: anything that accepts an httpx ``http_client`` works (OpenAI,
Anthropic, and most other httpx-based SDKs).
"""
from __future__ import annotations

import contextvars
import functools
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

from .store import InteractionStore
from .transport import AutoTransport, ExtraMetadata, KeyLike, RecordingTransport, ReplayTransport

Mode = str  # "auto" | "record" | "replay"

T = TypeVar("T")


@dataclass(frozen=True)
class _Scope:
    store: InteractionStore
    mode: Mode
    key: KeyLike
    simulate_timing: bool
    metadata: ExtraMetadata


# None outside any cassette scope → DynamicTransport passes through to network.
_active: contextvars.ContextVar[Optional[_Scope]] = contextvars.ContextVar(
    "agentrec_scope", default=None
)


def _transport_for(scope: _Scope, inner: httpx.AsyncBaseTransport) -> httpx.AsyncBaseTransport:
    if scope.mode == "record":
        return RecordingTransport(inner, scope.store, scope.key, scope.metadata)
    if scope.mode == "replay":
        return ReplayTransport(scope.store, scope.key, scope.simulate_timing)
    if scope.mode == "auto":
        return AutoTransport(
            inner, scope.store, scope.key, scope.simulate_timing, scope.metadata
        )
    raise ValueError(f"unknown mode {scope.mode!r}; expected auto|record|replay")


class DynamicTransport(httpx.AsyncBaseTransport):
    """Routes each request by the active :class:`cassette` scope.

    No scope → straight to *inner* (the real network), so a client built with
    :func:`async_client` is harmless when no cassette is active.
    """

    def __init__(self, inner: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        scope = _active.get()
        if scope is None:
            return await self._inner.handle_async_request(request)
        return await _transport_for(scope, self._inner).handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def async_client(
    *, inner: Optional[httpx.AsyncBaseTransport] = None, **httpx_kwargs
) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` that honours the active :class:`cassette` scope.

    Pass it to any httpx-based SDK via ``http_client=``.  ``inner`` overrides the
    real transport used when recording (handy in tests); extra kwargs go to
    ``httpx.AsyncClient``.
    """
    return httpx.AsyncClient(transport=DynamicTransport(inner), **httpx_kwargs)


class cassette:
    """Scope record/replay onto calls made through an :func:`async_client`.

    Usable as an async context manager or as a decorator on an async function.
    Parameters:

    * ``mode`` — ``"auto"`` (replay if recorded, else record), ``"record"``,
      or ``"replay"``.
    * ``id`` — fix every call in the scope to one cassette id.  Omit to derive a
      stable id per request (so distinct calls get distinct cassettes).
    * ``key`` — a custom ``request -> id`` callable, for advanced keying.
    * ``metadata`` — extra metadata merged into every recording made in this
      scope (e.g. ``{"category": "classify"}``); a dict or a per-request
      callable.  The migration report groups on a ``category`` tag.
    """

    def __init__(
        self,
        store: InteractionStore,
        *,
        mode: Mode = "auto",
        id: Optional[str] = None,
        key: KeyLike = None,
        simulate_timing: bool = False,
        metadata: ExtraMetadata = None,
    ) -> None:
        if mode not in ("auto", "record", "replay"):
            raise ValueError(f"unknown mode {mode!r}; expected auto|record|replay")
        if id is not None and key is not None:
            raise ValueError("pass either id or key, not both")
        self._scope = _Scope(
            store=store,
            mode=mode,
            key=id if id is not None else key,
            simulate_timing=simulate_timing,
            metadata=metadata,
        )
        self._token: Optional[contextvars.Token] = None

    async def __aenter__(self) -> "cassette":
        self._token = _active.set(self._scope)
        return self

    async def __aexit__(self, *exc) -> bool:
        assert self._token is not None
        _active.reset(self._token)
        self._token = None
        return False

    def __call__(self, fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            token = _active.set(self._scope)
            try:
                return await fn(*args, **kwargs)
            finally:
                _active.reset(token)

        return wrapper
