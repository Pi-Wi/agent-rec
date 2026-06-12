"""
Anthropic Messages adapter (``/v1/messages``).

Covers non-streaming JSON bodies (typed content blocks) and SSE streams
(``message_start`` / ``content_block_delta`` / ``message_delta`` events).

API specifics encoded here: ``max_tokens`` is required on every request;
auth is ``x-api-key`` plus an ``anthropic-version`` header; the newest models
reject sampling parameters, so ``temperature`` is only forwarded when the
recorded conversation carried one (the migration runner already drops it for
cross-provider runs).
"""
from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

from .base import (
    Conversation,
    DecodedResponse,
    DecodeError,
    ProviderAdapter,
    UnsupportedRequestError,
    sse_data_lines,
)

_API_VERSION = "2023-06-01"

# Anthropic has no native response_format/JSON mode, so a conversation that
# carries the neutral "caller asked for a JSON object" flag is emulated with a
# system-prompt suffix.  The no-fences wording matters: Claude models tend to
# wrap JSON in markdown fences, which breaks downstream parsers.
_JSON_MODE_SUFFIX = (
    "Respond with only a single JSON object. No prose, no markdown code fences."
)


def _blocks_to_text(content, *, what: str) -> str:
    """Plain text from ``content`` (string or list of typed blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "text"):
                kind = block.get("type") if isinstance(block, dict) else block
                raise UnsupportedRequestError(f"non-text {what} block {kind!r}")
            parts.append(block.get("text", ""))
        return "".join(parts)
    raise UnsupportedRequestError(f"unsupported {what} shape: {type(content).__name__}")


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"
    host_patterns = ("anthropic",)
    model_patterns = ("claude-",)
    api_key_env = "ANTHROPIC_API_KEY"

    messages_url = "https://api.anthropic.com/v1/messages"

    def extract_conversation(self, body: dict) -> Conversation:
        # Note: Anthropic requests have no response_format equivalent to
        # capture, so ``Conversation.response_format`` stays None here.
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            raise UnsupportedRequestError("request body has no messages list")
        if body.get("tools") or body.get("tool_choice"):
            raise UnsupportedRequestError("request uses tools")

        system = body.get("system")
        if system is not None:
            system = _blocks_to_text(system, what="system")

        conversation = Conversation(
            system=system,
            temperature=body.get("temperature"),
            max_tokens=body.get("max_tokens"),
        )
        for message in body["messages"]:
            role = message.get("role")
            if role not in ("user", "assistant"):
                raise UnsupportedRequestError(f"unsupported role {role!r}")
            text = _blocks_to_text(message.get("content"), what="message")
            conversation.messages.append({"role": role, "content": text})
        if not conversation.messages:
            raise UnsupportedRequestError("conversation has no user/assistant messages")
        return conversation

    def build_request(
        self,
        conversation: Conversation,
        model: str,
        *,
        max_tokens_default: int = 4096,
    ) -> Tuple[str, Dict[str, str], dict]:
        body: dict = {
            "model": model,
            "max_tokens": conversation.max_tokens or max_tokens_default,
            "messages": list(conversation.messages),
        }
        # JSON mode is emulated via the system prompt.  Composed locally into
        # the body only: the shared Conversation must never be mutated.
        system = conversation.system
        if conversation.response_format is not None:
            system = f"{system}\n\n{_JSON_MODE_SUFFIX}" if system else _JSON_MODE_SUFFIX
        if system:
            body["system"] = system
        if conversation.temperature is not None:
            body["temperature"] = conversation.temperature
        headers = {
            "x-api-key": self.api_key(),
            "anthropic-version": _API_VERSION,
            "Content-Type": "application/json",
        }
        return self.messages_url, headers, body

    def decode_response(self, payload: bytes, *, is_sse: bool) -> DecodedResponse:
        if is_sse:
            return self._decode_sse(payload)
        try:
            obj = json.loads(payload)
        except ValueError as exc:
            raise DecodeError(f"anthropic response is not valid JSON: {exc}") from None
        content = obj.get("content")
        if not isinstance(content, list):
            raise DecodeError("anthropic response has no content blocks")
        text = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return DecodedResponse(
            provider=self.name,
            model=obj.get("model"),
            text=text,
            finish_reason=obj.get("stop_reason"),
            usage=obj.get("usage"),
            streamed=False,
        )

    def _decode_sse(self, payload: bytes) -> DecodedResponse:
        text_parts = []
        stop_reason: Optional[str] = None
        model: Optional[str] = None
        usage: Optional[dict] = None
        saw_event = False
        for data in sse_data_lines(payload):
            try:
                obj = json.loads(data)
            except ValueError as exc:
                raise DecodeError(f"malformed anthropic SSE frame: {exc}") from None
            saw_event = True
            event_type = obj.get("type")
            if event_type == "message_start":
                message = obj.get("message") or {}
                model = message.get("model") or model
                usage = message.get("usage") or usage
            elif event_type == "content_block_delta":
                delta = obj.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text", ""))
            elif event_type == "message_delta":
                delta = obj.get("delta") or {}
                stop_reason = delta.get("stop_reason") or stop_reason
                if obj.get("usage"):
                    usage = {**(usage or {}), **obj["usage"]}
        if not saw_event:
            raise DecodeError("anthropic SSE stream contained no events")
        return DecodedResponse(
            provider=self.name,
            model=model,
            text="".join(text_parts),
            finish_reason=stop_reason,
            usage=usage,
            streamed=True,
        )
