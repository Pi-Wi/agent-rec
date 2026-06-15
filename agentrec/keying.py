"""
Derive a stable identity for a captured request.

Recording at the httpx layer means we see the request the SDK actually sent:
a method, a URL, and a JSON body.  ``fingerprint`` turns that into:

* ``cassette_id`` — the default key under which an interaction is stored and
  replayed.  It includes the model and the full request body (minus streaming
  flags), so the same prompt sent to two models — or with different sampling
  parameters — produces distinct recordings.
* ``semantic_key`` — the *prompt-level* identity.  When a provider adapter
  recognises the request, the key is a hash of the extracted provider-neutral
  conversation (system + messages + tools), so the same prompt recorded
  against OpenAI and Anthropic — or with different sampling parameters —
  hashes identically.  When no adapter matches (unknown host, images,
  non-chat endpoint), it falls back to a hash of the request body without the model
  and sampling/infrastructure knobs.  Two interactions that share a
  ``semantic_key`` ask the same thing — the grouping the migration report
  compares across.
* ``provider`` / ``model`` — pulled out so the corpus is browsable and a
  migration tool can filter by them without re-parsing every body.

Everything is best-effort: a non-JSON body still yields a usable key, just
without a model or semantic grouping.  Provider knowledge is delegated to the
adapter registry (:mod:`agentrec.providers`); this module only falls back to a
generic body normaliser when no adapter understands the request.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from .capture import CapturedInteraction

# Transport details that change neither the meaning nor the replayable
# identity of a request: excluded from BOTH keys.  ``model`` is handled
# separately (kept out of the semantic key but folded into the cassette id).
_TRANSPORT_FIELDS = frozenset({"stream", "stream_options"})

# Sampling / infrastructure knobs: they change *how* an answer is produced,
# not *what is being asked*.  Excluded from the semantic key only — the same
# prompt at temperature 0.0 and 0.7 must group together for the migration
# report — but kept in the cassette id, so record/replay still distinguishes
# requests that differ in these fields.
_SAMPLING_FIELDS = frozenset(
    {
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "max_completion_tokens",
        "seed",
        "user",
        "metadata",
        "frequency_penalty",
        "presence_penalty",
        "logit_bias",
        "logprobs",
        "top_logprobs",
        "service_tier",
        "store",
    }
)

_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class Fingerprint:
    """Identity of a request, derived from its method, URL and body."""

    provider: str
    model: Optional[str]
    semantic_key: str  # stable across model/provider/sampling swaps — groups comparable calls
    cassette_id: str  # default record/replay key (model- and request-specific)

    def as_metadata(self) -> dict:
        """The slice of the fingerprint worth persisting with the interaction."""
        return {
            "provider": self.provider,
            "model": self.model,
            "semantic_key": self.semantic_key,
        }


def _provider_from_host(host: str) -> str:
    """Provider name for a request host, resolved through the adapter registry.

    Delegating to the registry keeps provider knowledge in the adapters: a
    newly registered adapter (Gemini, or a custom override) tags its
    recordings correctly without editing this module.  Falls back to the bare
    host when no adapter matches.  (The match is by host substring, identical
    to the previous hard-coded openai/anthropic checks, so existing cassette
    ids are unchanged.)
    """
    # Deferred import: providers (lazily) imports keying for summaries.
    from .providers import adapter_for_host

    adapter = adapter_for_host(host)
    if adapter is not None:
        return adapter.name
    return host.lower() or "unknown"


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


def _canon_message(message: dict) -> dict:
    """A message stripped of provider-generated call ids.

    Tool-call ids (``call_…`` / ``toolu_…``) are minted per response, so the
    same logical conversation recorded on two providers carries different
    ids; identity must come from order, names and arguments instead.
    """
    out = {"role": message.get("role"), "content": message.get("content")}
    if message.get("role") == "tool":
        return out  # tool_call_id dropped; position links result to call
    calls = message.get("tool_calls")
    if calls:
        out["tool_calls"] = [
            {"name": call.get("name"), "arguments": call.get("arguments")} for call in calls
        ]
    return out


def _conversation_canon(host: str, body: dict) -> Optional[str]:
    """Canonical form of the request's provider-neutral conversation.

    Resolving through the provider adapter normalises away dialect differences
    (system as a leading message vs. a top-level field, plain strings vs. text
    blocks, tool_use blocks vs. tool_calls arrays), so the same logical prompt
    hashes identically across providers.  Sampling parameters are deliberately
    not part of the canon; tool definitions ARE (they shape the answer like a
    system prompt does), while an explicit ``tool_choice: auto`` equals the
    default.  Returns None when no adapter matches the host or the request
    uses features the adapter cannot translate (images, …) — callers then
    fall back to the generic body hash.

    Text-only conversations without tools produce the exact canon (and so the
    exact semantic keys) they always did.
    """
    # Deferred import: providers also (lazily) imports keying for summaries.
    from .providers import adapter_for_host

    adapter = adapter_for_host(host)
    if adapter is None:
        return None
    try:
        conversation = adapter.extract_conversation(body)
    except Exception:
        return None
    canon: dict = {
        "system": conversation.system,
        "messages": [_canon_message(message) for message in conversation.messages],
    }
    if conversation.tools:
        canon["tools"] = conversation.tools
    if conversation.tool_choice not in (None, "auto"):
        canon["tool_choice"] = conversation.tool_choice
    return _canonical(canon)


def fingerprint(request: httpx.Request) -> Fingerprint:
    """Compute a :class:`Fingerprint` for *request* (body must be readable)."""
    method = request.method
    path = request.url.path or ""
    host = request.url.host or ""
    provider = _provider_from_host(host)

    try:
        body = json.loads(request.content)
    except (ValueError, TypeError):
        body = None

    model: Optional[str] = None
    semantic_key: str
    if isinstance(body, dict):
        model = body.get("model")
        replay_view = {
            k: v for k, v in body.items() if k not in _TRANSPORT_FIELDS and k != "model"
        }
        canon = _canonical(replay_view)
        conversation_canon = _conversation_canon(host, body)
        if conversation_canon is not None:
            # Provider-neutral: no method/path/host — the same prompt asked of
            # OpenAI and Anthropic lands in the same group.
            semantic_key = _digest("conversation", conversation_canon)
        else:
            semantic_view = {k: v for k, v in replay_view.items() if k not in _SAMPLING_FIELDS}
            semantic_key = _digest(method, path, _canonical(semantic_view))
    elif body is not None:
        canon = _canonical(body)
        semantic_key = _digest(method, path, canon)
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
