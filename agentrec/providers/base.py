"""
Provider adapter interface: the only place provider-specific API knowledge lives.

A :class:`ProviderAdapter` owns three jobs for one LLM provider:

* ``extract_conversation`` — pull the provider-neutral conversation out of a
  recorded request body, so it can be re-asked of any other provider.
* ``build_request``       — turn a neutral conversation back into a concrete
  (url, headers, json body) for this provider, with fresh auth from the
  environment (recorded auth headers are redacted on disk).
* ``decode_response``     — turn recorded response bytes (one JSON document or
  a full SSE byte stream) into a :class:`DecodedResponse` with the assistant
  text a migration report compares on.

Adding a provider later means one new module subclassing this and a single
``register(...)`` call — nothing else in the library changes.

Scope: text and tool-use conversations.  Tool definitions, assistant tool
calls and tool results translate across providers; the *comparison* of tool
calls is selection + arguments only — recorded tools are never executed.
Requests using images or other non-text content raise
:class:`UnsupportedRequestError`, which the migration runner turns into a
clearly-reasoned skipped row rather than a crash.
"""
from __future__ import annotations

import json as _json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


class UnsupportedRequestError(Exception):
    """The recorded request uses features migration cannot translate yet."""


class DecodeError(Exception):
    """A recorded response could not be decoded into assistant text."""


class MissingAPIKeyError(Exception):
    """A live call was needed but the provider's API-key env var is unset."""


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation requested by an assistant response.

    ``arguments`` is the parsed argument object (usually a dict).  When a
    provider streamed argument JSON that does not parse, the raw string is
    kept instead — comparison still works (the string is one scalar), and
    nothing is silently dropped.
    """

    name: str
    arguments: object = None
    id: Optional[str] = None


@dataclass(frozen=True)
class DecodedResponse:
    """Normalised view of one LLM response, independent of provider format."""

    provider: str
    model: Optional[str]
    text: str
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    streamed: bool = False
    tool_calls: Tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class TokenUsage:
    """Disjoint token buckets normalised from a provider usage dict.

    ``input + cache_read + cache_write`` is the whole prompt side — the
    buckets never overlap, so a per-category price applies to each exactly
    once.  ``reasoning`` is informational: a subset of ``output`` (OpenAI
    o-series detail), never priced separately.  ``None`` means "the provider
    did not report this", not zero.  ``raw`` keeps the verbatim provider dict
    so a future, better normalisation can be applied retroactively — the
    cassette, not this object, stays the source of truth.
    """

    input: Optional[int] = None  # uncached prompt tokens
    cache_read: Optional[int] = None
    cache_write: Optional[int] = None
    output: Optional[int] = None  # includes reasoning tokens
    reasoning: Optional[int] = None  # informational subset of output
    raw: Optional[dict] = field(default=None, compare=False)

    @property
    def prompt_total(self) -> Optional[int]:
        """All prompt-side tokens (input + cache reads + cache writes)."""
        parts = [p for p in (self.input, self.cache_read, self.cache_write) if p is not None]
        return sum(parts) if parts else None


@dataclass
class Conversation:
    """Provider-neutral intermediate form of a chat request.

    ``messages`` hold ``user`` / ``assistant`` / ``tool`` roles; the system
    prompt is lifted out so each provider can place it where its API expects
    (top-level field vs. leading message).  Beyond plain-string ``content``,
    an assistant message may carry ``tool_calls``
    (``[{"id", "name", "arguments"}, ...]`` with parsed-dict arguments), and a
    ``tool`` message carries the result of one call
    (``{"role": "tool", "tool_call_id", "content"}``) — the neutral forms the
    dialect adapters translate to/from.

    ``tools`` are the request's tool definitions in neutral form
    (``[{"name", "description", "parameters"}, ...]``, ``parameters`` being
    the JSON schema).  A tool may also carry ``"strict": bool`` — OpenAI's
    strict-schema function flag; it rides *inside* the tool dict but is held
    out of the prompt's semantic identity (see :mod:`agentrec.keying`), so the
    same tool with and without strict groups together.  ``tool_choice`` is
    ``None`` (provider default), ``"auto"``, ``"required"``, ``"none"`` or
    ``{"name": <tool>}`` (forced).

    ``response_format`` is the provider-neutral "the caller asked for
    structured output".  Two shapes are carried: ``{"type": "json_object"}``
    (free-form JSON mode — providers with a native mode re-emit it, others
    emulate it via the system prompt) and
    ``{"type": "json_schema", "json_schema": {...}}`` (a *strict* schema —
    re-emitted only on targets that enforce it natively; non-native targets
    raise :class:`UnsupportedRequestError` from ``build_request` rather than
    pretend a prompt nudge enforces a schema).  ``parallel_tool_calls`` is the
    neutral copy of OpenAI's same-named flag.  None of these three are part of
    the prompt's semantic identity: the same prompt with and without them
    groups under one ``semantic_key``.
    """

    system: Optional[str] = None
    messages: List[dict] = field(default_factory=list)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[dict] = None
    tools: Optional[List[dict]] = None
    tool_choice: Optional[object] = None
    parallel_tool_calls: Optional[bool] = None


def generic_token_usage(usage: Optional[dict]) -> TokenUsage:
    """Provider-agnostic :class:`TokenUsage` (input/output only, no cache)."""
    if not isinstance(usage, dict):
        return TokenUsage()

    def first_int(*keys: str) -> Optional[int]:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int):
                return value
        return None

    return TokenUsage(
        input=first_int("input_tokens", "prompt_tokens"),
        output=first_int("output_tokens", "completion_tokens"),
        raw=usage,
    )


def _fmt_tool_arguments(arguments: object) -> str:
    """Canonical one-line rendering of a tool call's arguments."""
    if isinstance(arguments, str):
        return arguments
    try:
        return _json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(arguments)


def format_conversation(conversation: Conversation) -> str:
    """Human-readable rendering of a conversation (summaries, judge prompts).

    A bare single user message renders as just its text — the common case for
    pipeline-style corpora — while anything richer gets ``[role]`` markers.
    Assistant tool calls and tool results render as explicit lines so a judge
    (or a report reader) sees the full agent step.
    """
    only = conversation.messages[0] if len(conversation.messages) == 1 else None
    if (
        conversation.system is None
        and only is not None
        and only.get("role") == "user"
        and not only.get("tool_calls")
    ):
        return only.get("content") or ""
    parts = []
    if conversation.system:
        parts.append(f"[system] {conversation.system}")
    for message in conversation.messages:
        role = message.get("role")
        content = message.get("content")
        if role == "tool":
            parts.append(f"[tool result] {content or ''}")
            continue
        if content:
            parts.append(f"[{role}] {content}")
        for call in message.get("tool_calls") or ():
            parts.append(
                f"[{role} tool_call] {call.get('name')}"
                f"({_fmt_tool_arguments(call.get('arguments'))})"
            )
    return "\n\n".join(parts)


def render_response(decoded: DecodedResponse) -> str:
    """Text plus canonical tool-call lines — the comparable form of a response.

    For text-only responses this is exactly ``decoded.text``, so judge-verdict
    cache keys and comparator behaviour on existing corpora are unchanged.
    For tool-calling responses it appends one deterministic line per call, so
    text comparators (and the judge) see *what the model decided to do*
    instead of an empty string.
    """
    parts = [decoded.text] if decoded.text else []
    for call in decoded.tool_calls:
        parts.append(f"[tool_call] {call.name}({_fmt_tool_arguments(call.arguments)})")
    return "\n".join(parts)


def sse_data_lines(payload: bytes) -> List[str]:
    """Extract the ``data:`` payloads from a raw SSE byte stream.

    The transport records arbitrary byte chunks that may split an SSE frame
    (even mid-JSON), so callers must join all chunks into one payload *before*
    calling this — never parse chunk-by-chunk.
    """
    text = payload.decode("utf-8", "replace")
    out: List[str] = []
    # The SSE spec allows CRLF as well as LF between lines/frames.
    for frame in re.split(r"\r?\n\r?\n", text):
        datas: List[str] = []
        for line in frame.splitlines():
            if line == "data":
                datas.append("")  # spec: a bare "data" line carries an empty payload
            elif line.startswith("data:"):
                value = line[5:]
                # Spec: strip exactly ONE leading space; anything further is
                # payload (significant for raw text deltas, harmless for JSON).
                datas.append(value[1:] if value.startswith(" ") else value)
        if datas:
            # Per the SSE spec, multiple data lines in one frame join with \n.
            out.append("\n".join(datas))
    return out


class ProviderAdapter(ABC):
    """One LLM provider's request/response dialect. See module docstring."""

    name: str
    host_patterns: Tuple[str, ...]  # substrings matched against the URL host
    model_patterns: Tuple[str, ...]  # model-id prefixes, e.g. ("claude-",)
    api_key_env: str

    def matches_host(self, host: str) -> bool:
        host = host.lower()
        return any(pattern in host for pattern in self.host_patterns)

    def matches_model(self, model: str) -> bool:
        model = model.lower()
        return any(model.startswith(pattern) for pattern in self.model_patterns)

    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise MissingAPIKeyError(
                f"{self.api_key_env} is not set; a live call to {self.name} "
                "needs it (recorded auth headers are redacted)."
            )
        return key

    def normalize_usage(self, usage: Optional[dict]) -> TokenUsage:
        """Disjoint :class:`TokenUsage` from this provider's usage dict.

        The base implementation is a best-effort generic mapping (no cache
        knowledge); providers with cache/reasoning detail override it.
        """
        return generic_token_usage(usage)

    # --- target capabilities ------------------------------------------------
    # The migration runner consults these so it can note *honestly* on a row
    # when a field the baseline set cannot ride to this target — versus
    # silently dropping it.  Defaults say "this dialect does not carry it";
    # an adapter whose ``build_request`` re-emits the field overrides to True.

    def carries_parallel_tool_calls(self) -> bool:
        """Whether ``build_request`` preserves ``parallel_tool_calls``."""
        return False

    def carries_function_strict(self) -> bool:
        """Whether ``build_request`` preserves per-tool ``strict`` schema flags."""
        return False

    @abstractmethod
    def extract_conversation(self, body: dict) -> Conversation:
        """Neutral conversation from this provider's request body.

        Raises :class:`UnsupportedRequestError` for tools/images/n>1 etc.
        """

    @abstractmethod
    def build_request(
        self,
        conversation: Conversation,
        model: str,
        *,
        max_tokens_default: int = 4096,
        stream: bool = False,
    ) -> Tuple[str, Dict[str, str], dict]:
        """(url, headers, json_body) for a fresh request, with fresh env auth.

        ``stream=True`` produces this dialect's *streaming* form (so the caller
        can measure a real time-to-first-chunk, comparable to a streamed
        baseline's): for the chat-completions dialects that means
        ``stream: true`` in the body, for Gemini the ``streamGenerateContent``
        endpoint.  ``stream``/``stream_options`` are excluded from a request's
        cassette identity (see :mod:`agentrec.keying`), so the same prompt keys
        the same whether it was recorded streaming or not."""

    @abstractmethod
    def decode_response(self, payload: bytes, *, is_sse: bool) -> DecodedResponse:
        """Decode response bytes (joined chunks) into a :class:`DecodedResponse`."""
