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

Scope (v1): text-only conversations.  Requests using tools, images or other
non-text content raise :class:`UnsupportedRequestError`, which the migration
runner turns into a clearly-reasoned skipped row rather than a crash.
"""
from __future__ import annotations

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
class DecodedResponse:
    """Normalised view of one LLM response, independent of provider format."""

    provider: str
    model: Optional[str]
    text: str
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    streamed: bool = False


@dataclass
class Conversation:
    """Provider-neutral intermediate form of a chat request.

    ``messages`` hold only ``user`` / ``assistant`` roles with plain-string
    content; the system prompt is lifted out so each provider can place it
    where its API expects (top-level field vs. leading message).

    ``response_format`` is the provider-neutral "the caller asked for a JSON
    object".  Only ``{"type": "json_object"}`` is carried; providers with a
    native JSON mode re-emit it, others emulate it via the system prompt.
    It is *not* part of the prompt's semantic identity: the same prompt with
    and without JSON mode groups under one ``semantic_key``.
    """

    system: Optional[str] = None
    messages: List[Dict[str, str]] = field(default_factory=list)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[dict] = None


def format_conversation(conversation: Conversation) -> str:
    """Human-readable rendering of a conversation (summaries, judge prompts).

    A bare single user message renders as just its text — the common case for
    pipeline-style corpora — while anything richer gets ``[role]`` markers.
    """
    if conversation.system is None and len(conversation.messages) == 1:
        return conversation.messages[0]["content"]
    parts = []
    if conversation.system:
        parts.append(f"[system] {conversation.system}")
    for message in conversation.messages:
        parts.append(f"[{message['role']}] {message['content']}")
    return "\n\n".join(parts)


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
    ) -> Tuple[str, Dict[str, str], dict]:
        """(url, headers, json_body) for a fresh, non-streaming request."""

    @abstractmethod
    def decode_response(self, payload: bytes, *, is_sse: bool) -> DecodedResponse:
        """Decode response bytes (joined chunks) into a :class:`DecodedResponse`."""
