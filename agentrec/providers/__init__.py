"""
Provider adapter registry plus interaction-level helpers built on it.

``register`` / ``adapter_for_provider`` / ``adapter_for_model`` /
``adapter_for_host`` make providers pluggable: a new provider is one module
subclassing :class:`ProviderAdapter` and one ``register`` call.

``decode_interaction`` / ``conversation_of`` / ``build_summary`` operate on a
:class:`~agentrec.capture.CapturedInteraction`, resolving the right adapter
from its metadata or URL — including legacy cassettes recorded before any
metadata existed.
"""
from __future__ import annotations

import json
from typing import List, Optional
from urllib.parse import urlsplit

from ..capture import CapturedInteraction
from .anthropic import AnthropicAdapter
from .gemini import GeminiAdapter
from .base import (
    Conversation,
    DecodedResponse,
    DecodeError,
    MissingAPIKeyError,
    ProviderAdapter,
    TokenUsage,
    ToolCall,
    UnsupportedRequestError,
    format_conversation,
    generic_token_usage,
    render_response,
    sse_data_lines,
)
from .openai import OpenAIAdapter

__all__ = [
    "Conversation",
    "DecodedResponse",
    "DecodeError",
    "MissingAPIKeyError",
    "ProviderAdapter",
    "TokenUsage",
    "ToolCall",
    "UnsupportedRequestError",
    "format_conversation",
    "render_response",
    "sse_data_lines",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "GeminiAdapter",
    "register",
    "adapters",
    "adapter_for_provider",
    "adapter_for_model",
    "adapter_for_host",
    "decode_interaction",
    "conversation_of",
    "build_summary",
    "usage_of",
]

_ADAPTERS: List[ProviderAdapter] = []


def register(adapter: ProviderAdapter) -> None:
    """Make *adapter* discoverable by provider name, model prefix and host.

    Later registrations win: registering an adapter that matches the same
    name/host/model patterns as a built-in *overrides* the built-in, so a
    custom OpenAI adapter (e.g. one speaking the Responses API) can replace
    the stock one without touching the library.
    """
    _ADAPTERS.append(adapter)


def adapters() -> List[ProviderAdapter]:
    return list(_ADAPTERS)


def adapter_for_provider(name: str) -> ProviderAdapter:
    for adapter in reversed(_ADAPTERS):  # later registrations win
        if adapter.name == name.lower():
            return adapter
    known = ", ".join(a.name for a in _ADAPTERS)
    raise LookupError(f"no provider adapter named {name!r} (known: {known})")


def adapter_for_model(model: str) -> ProviderAdapter:
    for adapter in reversed(_ADAPTERS):  # later registrations win
        if adapter.matches_model(model):
            return adapter
    known = ", ".join(a.name for a in _ADAPTERS)
    raise LookupError(
        f"cannot infer a provider from model {model!r} (known providers: {known}); "
        "pass an explicit target provider"
    )


def adapter_for_host(host: str) -> Optional[ProviderAdapter]:
    for adapter in reversed(_ADAPTERS):  # later registrations win
        if adapter.matches_host(host):
            return adapter
    return None


register(OpenAIAdapter())
register(AnthropicAdapter())
register(GeminiAdapter())


def _adapter_for_interaction(interaction: CapturedInteraction) -> ProviderAdapter:
    provider = (interaction.metadata or {}).get("provider")
    if provider:
        try:
            return adapter_for_provider(provider)
        except LookupError:
            pass  # fall back to the URL host below
    host = urlsplit(interaction.request.url).hostname or ""
    adapter = adapter_for_host(host)
    if adapter is None:
        raise DecodeError(f"no provider adapter for host {host!r}")
    return adapter


def _header(interaction: CapturedInteraction, name: bytes) -> Optional[bytes]:
    """Last value of response header *name* (lowercased match), or None."""
    found: Optional[bytes] = None
    for header_name, value in interaction.response_headers:
        if header_name.lower() == name:
            found = value
    return found


def _is_sse(interaction: CapturedInteraction) -> bool:
    content_type = _header(interaction, b"content-type")
    return content_type is not None and b"text/event-stream" in content_type.lower()


def _response_payload(interaction: CapturedInteraction) -> bytes:
    """Joined response bytes, decompressed per the recorded Content-Encoding.

    The transport tees raw on-the-wire bytes, so a gzip/deflate/br response is
    stored compressed (replay re-decompresses via httpx using the header).  The
    corpus tooling reads chunks directly, so it must undo the same encoding here
    before any JSON/SSE parsing.
    """
    payload = b"".join(chunk.data for chunk in interaction.chunks)
    encoding = _header(interaction, b"content-encoding")
    if not encoding:
        return payload
    encoding = encoding.decode("ascii", "ignore").strip().lower()
    # Multiple codings can be comma-separated, applied left-to-right on the way
    # out; undo them right-to-left.
    for coding in reversed([c.strip() for c in encoding.split(",") if c.strip()]):
        if coding in ("identity", ""):
            continue
        try:
            payload = _decompress(coding, payload)
        except Exception as exc:  # corrupt/short stream, unknown codec, etc.
            raise DecodeError(
                f"could not decode {coding!r} content-encoding: {exc}"
            ) from None
    return payload


def _decompress(coding: str, payload: bytes) -> bytes:
    if coding == "gzip":
        import gzip

        return gzip.decompress(payload)
    if coding == "deflate":
        import zlib

        try:
            return zlib.decompress(payload)
        except zlib.error:
            # Raw DEFLATE without a zlib header (some servers send this).
            return zlib.decompress(payload, -zlib.MAX_WBITS)
    if coding in ("br", "brotli"):
        try:
            import brotli  # optional dependency
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise DecodeError(
                "response uses brotli content-encoding but the 'brotli' "
                "package is not installed"
            ) from exc
        return brotli.decompress(payload)
    if coding == "zstd":
        try:
            import zstandard  # optional dependency
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise DecodeError(
                "response uses zstd content-encoding but the 'zstandard' "
                "package is not installed"
            ) from exc
        return zstandard.ZstdDecompressor().decompress(payload)
    raise DecodeError(f"unsupported content-encoding {coding!r}")


def decode_interaction(interaction: CapturedInteraction) -> DecodedResponse:
    """Decode a recorded interaction's response into assistant text."""
    if interaction.response_status != 200:
        raise DecodeError(f"response status {interaction.response_status}, not 200")
    payload = _response_payload(interaction)
    adapter = _adapter_for_interaction(interaction)
    return adapter.decode_response(payload, is_sse=_is_sse(interaction))


def usage_of(decoded: DecodedResponse) -> TokenUsage:
    """Disjoint :class:`TokenUsage` for a decoded response.

    Resolves the response's provider adapter for its normalisation rules
    (OpenAI nests cached/reasoning detail inside the totals, Anthropic keeps
    cache traffic additive); an unknown provider degrades to the generic
    input/output mapping.
    """
    try:
        adapter = adapter_for_provider(decoded.provider)
    except LookupError:
        return generic_token_usage(decoded.usage)
    return adapter.normalize_usage(decoded.usage)


def conversation_of(interaction: CapturedInteraction) -> Conversation:
    """Provider-neutral conversation from a recorded interaction's request."""
    adapter = _adapter_for_interaction(interaction)
    try:
        body = json.loads(interaction.request.content)
    except ValueError:
        raise UnsupportedRequestError("request body is not JSON") from None
    return adapter.extract_conversation(body)


def build_summary(interaction: CapturedInteraction) -> dict:
    """Best-effort human-readable summary of an interaction.

    Used by :class:`~agentrec.store.FileStore` as the first block of every
    cassette so a file opens with the prompt and answer in plain text.  Each
    part degrades independently — an undecodable response still yields a
    summary with the prompt — and an empty dict means "no summary".
    """
    metadata = interaction.metadata or {}
    summary: dict = {}

    provider = metadata.get("provider")
    model = metadata.get("model")
    semantic_key = metadata.get("semantic_key")
    if not (provider and semantic_key):
        # Legacy cassette: recompute identity from the stored request.
        from ..keying import fingerprint_of

        try:
            fp = fingerprint_of(interaction)
            provider = provider or fp.provider
            model = model or fp.model
            semantic_key = semantic_key or fp.semantic_key
        except Exception:
            pass

    try:
        summary["prompt"] = format_conversation(conversation_of(interaction))
    except Exception:
        pass
    try:
        decoded = decode_interaction(interaction)
        # render_response: text plus tool-call lines, so a tool-calling
        # cassette opens with what the model decided to do.
        summary["response"] = render_response(decoded)
        model = model or decoded.model
    except Exception:
        pass
    if not summary:
        return {}

    head = {"provider": provider, "model": model}
    head.update(summary)
    head["semantic_key"] = semantic_key
    if metadata.get("recorded_at"):
        head["recorded_at"] = metadata["recorded_at"]
    return head
