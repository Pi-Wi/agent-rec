"""
OpenAI chat-completions adapter (``/v1/chat/completions``).

Covers both response shapes the transport records: non-streaming JSON bodies
and SSE streams of ``chat.completion.chunk`` deltas.

Scope: this adapter speaks the **chat-completions** dialect only.  Recordings
made against the newer Responses API (``/v1/responses``) are not decodable
yet — register a custom adapter to override this one if you need that (see
``agentrec.providers.register``).  o-series reasoning models are supported as
chat-completions targets: they reject ``max_tokens`` and sampling params, so
``build_request`` sends ``max_completion_tokens`` and drops ``temperature``
for them.
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

# Request-body fields v1 cannot translate faithfully; their presence makes the
# whole request unsupported rather than silently changing its meaning.
# ``response_format`` is NOT here: ``{"type": "json_object"}`` is captured as
# the neutral ``Conversation.response_format``.  The ``json_schema`` variant
# stays unsupported — strict structured output can't be faithfully emulated on
# providers without it, and a prompt nudge does not enforce a schema.
_UNSUPPORTED_FIELDS = ("tools", "tool_choice", "functions", "function_call")


def _content_to_text(content) -> str:
    """Plain text from a message ``content`` (string or list of text parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not (isinstance(part, dict) and part.get("type") == "text"):
                raise UnsupportedRequestError(
                    f"non-text content part {part.get('type') if isinstance(part, dict) else part!r}"
                )
            parts.append(part.get("text", ""))
        return "".join(parts)
    raise UnsupportedRequestError(f"unsupported content shape: {type(content).__name__}")


class OpenAIAdapter(ProviderAdapter):
    name = "openai"
    host_patterns = ("openai",)
    model_patterns = ("gpt-", "chatgpt-", "o1", "o3", "o4")
    api_key_env = "OPENAI_API_KEY"

    chat_url = "https://api.openai.com/v1/chat/completions"

    def extract_conversation(self, body: dict) -> Conversation:
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            raise UnsupportedRequestError("request body has no messages list")
        for field_name in _UNSUPPORTED_FIELDS:
            if body.get(field_name):
                raise UnsupportedRequestError(f"request uses {field_name!r}")
        if body.get("n") not in (None, 1):
            raise UnsupportedRequestError("request uses n > 1")

        response_format = None
        requested_format = body.get("response_format")
        if requested_format:
            format_type = (
                requested_format.get("type") if isinstance(requested_format, dict) else None
            )
            if format_type == "json_object":
                response_format = {"type": "json_object"}
            elif format_type != "text":
                raise UnsupportedRequestError(
                    f"request uses response_format type {format_type!r}"
                )

        conversation = Conversation(
            temperature=body.get("temperature"),
            max_tokens=body.get("max_tokens") or body.get("max_completion_tokens"),
            response_format=response_format,
        )
        for message in body["messages"]:
            role = message.get("role")
            if message.get("tool_calls") or role in ("tool", "function"):
                raise UnsupportedRequestError("request contains tool calls")
            text = _content_to_text(message.get("content"))
            if role in ("system", "developer"):
                if conversation.messages:
                    raise UnsupportedRequestError("system message after conversation start")
                conversation.system = (
                    text if conversation.system is None else conversation.system + "\n\n" + text
                )
            elif role in ("user", "assistant"):
                conversation.messages.append({"role": role, "content": text})
            else:
                raise UnsupportedRequestError(f"unsupported role {role!r}")
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
        messages = []
        if conversation.system:
            messages.append({"role": "system", "content": conversation.system})
        messages.extend(conversation.messages)
        body: dict = {"model": model, "messages": messages}
        # o-series reasoning models reject max_tokens (use max_completion_tokens
        # instead) and 400 on sampling params like temperature.
        reasoning = model.startswith(("o1", "o3", "o4"))
        # max_tokens is optional on this API: only carry it over when the
        # baseline set it; never invent a cap the original call didn't have.
        if conversation.max_tokens is not None:
            body["max_completion_tokens" if reasoning else "max_tokens"] = conversation.max_tokens
        if conversation.temperature is not None and not reasoning:
            body["temperature"] = conversation.temperature
        if conversation.response_format is not None:
            # Native JSON mode: re-emit on this provider's own dialect.
            body["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.api_key()}",
            "Content-Type": "application/json",
        }
        return self.chat_url, headers, body

    def decode_response(self, payload: bytes, *, is_sse: bool) -> DecodedResponse:
        if is_sse:
            return self._decode_sse(payload)
        try:
            obj = json.loads(payload)
        except ValueError as exc:
            raise DecodeError(f"openai response is not valid JSON: {exc}") from None
        choices = obj.get("choices") or []
        if not choices:
            raise DecodeError("openai response has no choices")
        message = choices[0].get("message") or {}
        return DecodedResponse(
            provider=self.name,
            model=obj.get("model"),
            text=message.get("content") or "",
            finish_reason=choices[0].get("finish_reason"),
            usage=obj.get("usage"),
            streamed=False,
        )

    def _decode_sse(self, payload: bytes) -> DecodedResponse:
        text_parts = []
        finish_reason: Optional[str] = None
        model: Optional[str] = None
        usage: Optional[dict] = None
        saw_chunk = False
        for data in sse_data_lines(payload):
            if data.strip() == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except ValueError as exc:
                raise DecodeError(f"malformed openai SSE frame: {exc}") from None
            saw_chunk = True
            model = obj.get("model") or model
            if obj.get("usage"):
                usage = obj["usage"]
            choices = obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    text_parts.append(piece)
                finish_reason = choices[0].get("finish_reason") or finish_reason
        if not saw_chunk:
            raise DecodeError("openai SSE stream contained no chunks")
        return DecodedResponse(
            provider=self.name,
            model=model,
            text="".join(text_parts),
            finish_reason=finish_reason,
            usage=usage,
            streamed=True,
        )
