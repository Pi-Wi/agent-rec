"""
Derive a stable identity for a captured request.

Recording at the httpx layer means we see the request the SDK actually sent:
a method, a URL, and a JSON body.  ``fingerprint`` turns that into:

* ``cassette_id`` — the default key under which an interaction is stored and
  replayed.  It includes the model, so the same prompt sent to two models
  produces two distinct recordings.
* ``semantic_key`` — a hash of the request *without* the model (or other
  non-semantic fields).  Two interactions that share a ``semantic_key`` are the
  same logical call answered by (potentially) different models — the grouping a
  future migration report needs to compare one model against another.
* ``provider`` / ``model`` — pulled out so the corpus is browsable and a
  migration tool can filter by them without re-parsing every body.

Everything is best-effort: a non-JSON body still yields a usable key, just
without a model or semantic grouping.  No provider-specific code lives here —
OpenAI and Anthropic both send a top-level ``model`` and ``messages`` in a JSON
body, so one generic normaliser covers both (and most other httpx-based SDKs).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from .capture import CapturedInteraction

# Fields that do not change the *meaning* of a request, so they are excluded
# from the semantic key.  ``model`` is handled separately (kept out of the
# semantic key but folded into the cassette id).
_NON_SEMANTIC_FIELDS = frozenset({"stream", "stream_options"})

_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class Fingerprint:
    """Identity of a request, derived from its method, URL and body."""

    provider: str
    model: Optional[str]
    semantic_key: str  # stable across model swaps — groups comparable calls
    cassette_id: str  # default record/replay key (model-specific)

    def as_metadata(self) -> dict:
        """The slice of the fingerprint worth persisting with the interaction."""
        return {
            "provider": self.provider,
            "model": self.model,
            "semantic_key": self.semantic_key,
        }


def _provider_from_host(host: str) -> str:
    host = host.lower()
    if "anthropic" in host:
        return "anthropic"
    if "openai" in host:
        return "openai"
    return host or "unknown"


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _sanitize(text: str) -> str:
    return _UNSAFE_ID_CHARS.sub("-", text).strip("-") or "x"


def fingerprint(request: httpx.Request) -> Fingerprint:
    """Compute a :class:`Fingerprint` for *request* (body must be readable)."""
    method = request.method
    path = request.url.path or ""
    provider = _provider_from_host(request.url.host or "")

    try:
        body = json.loads(request.content)
    except (ValueError, TypeError):
        body = None

    model: Optional[str] = None
    if isinstance(body, dict):
        model = body.get("model")
        semantic = {k: v for k, v in body.items() if k not in _NON_SEMANTIC_FIELDS and k != "model"}
        canon = _canonical(semantic)
    elif body is not None:
        canon = _canonical(body)
    else:
        # Non-JSON body: fall back to the raw bytes so the key is still stable.
        canon = request.content.decode("utf-8", "replace")

    semantic_key = _digest(method, path, canon)
    model_hash = _digest(method, path, str(model), canon)
    cassette_id = "_".join(
        (_sanitize(provider), _sanitize(model or "unknown"), model_hash[:16])
    )
    return Fingerprint(
        provider=provider,
        model=model,
        semantic_key=semantic_key[:32],
        cassette_id=cassette_id,
    )


def fingerprint_of(interaction: CapturedInteraction) -> Fingerprint:
    """Fingerprint a *stored* interaction by rebuilding its request.

    Lets corpus tooling (migration report, annotate) derive provider, model
    and semantic_key even for legacy cassettes recorded before metadata
    stamping existed.
    """
    req = interaction.request
    return fingerprint(httpx.Request(req.method, req.url, content=req.content))


def default_key(request: httpx.Request) -> str:
    """Default per-request cassette id: the model-specific fingerprint key."""
    return fingerprint(request).cassette_id
