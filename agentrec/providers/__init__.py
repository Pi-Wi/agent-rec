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
from .base import (
    Conversation,
    DecodedResponse,
    DecodeError,
    MissingAPIKeyError,
    ProviderAdapter,
    UnsupportedRequestError,
    format_conversation,
    sse_data_lines,
)
from .openai import OpenAIAdapter

__all__ = [
    "Conversation",
    "DecodedResponse",
    "DecodeError",
    "MissingAPIKeyError",
    "ProviderAdapter",
    "UnsupportedRequestError",
    "format_conversation",
    "sse_data_lines",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "register",
    "adapters",
    "adapter_for_provider",
    "adapter_for_model",
    "adapter_for_host",
    "decode_interaction",
    "conversation_of",
    "build_summary",
]

_ADAPTERS: List[ProviderAdapter] = []


def register(adapter: ProviderAdapter) -> None:
    """Make *adapter* discoverable by provider name, model prefix and host."""
    _ADAPTERS.append(adapter)


def adapters() -> List[ProviderAdapter]:
    return list(_ADAPTERS)


def adapter_for_provider(name: str) -> ProviderAdapter:
    for adapter in _ADAPTERS:
        if adapter.name == name.lower():
            return adapter
    known = ", ".join(a.name for a in _ADAPTERS)
    raise LookupError(f"no provider adapter named {name!r} (known: {known})")


def adapter_for_model(model: str) -> ProviderAdapter:
    for adapter in _ADAPTERS:
        if adapter.matches_model(model):
            return adapter
    known = ", ".join(a.name for a in _ADAPTERS)
    raise LookupError(
        f"cannot infer a provider from model {model!r} (known providers: {known}); "
        "pass an explicit target provider"
    )


def adapter_for_host(host: str) -> Optional[ProviderAdapter]:
    for adapter in _ADAPTERS:
        if adapter.matches_host(host):
            return adapter
    return None


register(OpenAIAdapter())
register(AnthropicAdapter())


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


def _is_sse(interaction: CapturedInteraction) -> bool:
    for name, value in interaction.response_headers:
        if name.lower() == b"content-type":
            return b"text/event-stream" in value.lower()
    return False


def decode_interaction(interaction: CapturedInteraction) -> DecodedResponse:
    """Decode a recorded interaction's response into assistant text."""
    if interaction.response_status != 200:
        raise DecodeError(f"response status {interaction.response_status}, not 200")
    payload = b"".join(chunk.data for chunk in interaction.chunks)
    adapter = _adapter_for_interaction(interaction)
    return adapter.decode_response(payload, is_sse=_is_sse(interaction))


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
        summary["response"] = decoded.text
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
