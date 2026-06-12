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
    TokenUsage,
    ToolCall,
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


def _extract_tools(body: dict) -> "list[dict] | None":
    """Neutral tool definitions from an Anthropic ``tools`` array."""
    raw_tools = body.get("tools")
    if not raw_tools:
        return None
    tools = []
    for entry in raw_tools:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise UnsupportedRequestError("tool definition has no name")
        if entry.get("type") not in (None, "custom"):
            # Server-side tools (web_search, computer use, …) execute on
            # Anthropic's infrastructure and have no cross-provider neutral
            # form.
            raise UnsupportedRequestError(f"unsupported tool type {entry['type']!r}")
        tool = {"name": entry["name"]}
        if entry.get("description") is not None:
            tool["description"] = entry["description"]
        if entry.get("input_schema") is not None:
            tool["parameters"] = entry["input_schema"]
        tools.append(tool)
    return tools


def _extract_tool_choice(body: dict) -> object:
    """Neutral tool_choice from the Anthropic dialect."""
    raw = body.get("tool_choice")
    if raw is None:
        return None
    kind = raw.get("type") if isinstance(raw, dict) else None
    if kind == "auto":
        return "auto"
    if kind == "any":
        return "required"
    if kind == "none":
        return "none"
    if kind == "tool" and raw.get("name"):
        return {"name": raw["name"]}
    raise UnsupportedRequestError(f"unsupported tool_choice {raw!r}")


def _extract_message(message: dict, out: "list[dict]") -> None:
    """Append the neutral message(s) for one Anthropic message to *out*.

    Block order is preserved: a user message mixing ``tool_result`` blocks
    and text becomes one neutral ``tool`` message per result plus a ``user``
    message for the text; an assistant message mixing text and ``tool_use``
    becomes one assistant message carrying both.
    """
    role = message.get("role")
    content = message.get("content")
    if isinstance(content, str):
        out.append({"role": role, "content": content})
        return
    if not isinstance(content, list):
        raise UnsupportedRequestError(
            f"unsupported message shape: {type(content).__name__}"
        )

    text_parts: "list[str]" = []
    tool_calls: "list[dict]" = []
    for block in content:
        kind = block.get("type") if isinstance(block, dict) else None
        if kind == "text":
            text_parts.append(block.get("text", ""))
        elif kind == "tool_use" and role == "assistant":
            tool_calls.append(
                {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "arguments": block.get("input") if block.get("input") is not None else {},
                }
            )
        elif kind == "tool_result" and role == "user":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id"),
                    "content": _blocks_to_text(
                        block.get("content") or "", what="tool_result"
                    ),
                }
            )
        else:
            raise UnsupportedRequestError(f"non-text message block {kind!r}")
    text = "".join(text_parts)
    if tool_calls:
        out.append({"role": "assistant", "content": text, "tool_calls": tool_calls})
    elif text or not (out and out[-1].get("role") == "tool"):
        # Emit the text message; a user message that was ONLY tool_result
        # blocks already emitted its results and adds nothing more.
        out.append({"role": role, "content": text})


def _messages_to_anthropic(messages: "list[dict]") -> "list[dict]":
    """Anthropic messages from neutral ones.

    This API requires strictly alternating user/assistant roles, so neutral
    ``tool`` messages (which map to user-role ``tool_result`` blocks) merge
    with adjacent user content into one message.  Ids missing from hand-built
    conversations are synthesized in call order and handed to id-less results
    in the same order, keeping the call/result linkage intact.
    """
    synthesized_ids: "list[str]" = []
    synthesized_count = 0
    out: "list[dict]" = []

    def emit(role: str, blocks: "list[dict]") -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})

    for message in messages:
        role = message.get("role")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if not call_id:
                call_id = synthesized_ids.pop(0) if synthesized_ids else "call_0"
            emit(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": message.get("content") or "",
                    }
                ],
            )
        elif message.get("tool_calls"):
            blocks: "list[dict]" = []
            if message.get("content"):
                blocks.append({"type": "text", "text": message["content"]})
            for call in message["tool_calls"]:
                call_id = call.get("id")
                if not call_id:
                    call_id = f"call_{synthesized_count}"
                    synthesized_count += 1
                    synthesized_ids.append(call_id)
                arguments = call.get("arguments")
                if arguments is not None and not isinstance(arguments, dict):
                    # tool_use input must be an object; a string here means the
                    # recorded argument JSON never parsed.
                    raise UnsupportedRequestError(
                        "assistant tool-call arguments are not a JSON object"
                    )
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": call.get("name"),
                        "input": arguments if arguments is not None else {},
                    }
                )
            emit("assistant", blocks)
        else:
            emit(role, [{"type": "text", "text": message.get("content") or ""}])

    # Collapse single-text-block messages back to plain strings: the wire
    # shape text-only conversations always had.
    for message in out:
        blocks = message["content"]
        if len(blocks) == 1 and blocks[0].get("type") == "text":
            message["content"] = blocks[0]["text"]
    return out


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

        system = body.get("system")
        if system is not None:
            system = _blocks_to_text(system, what="system")

        conversation = Conversation(
            system=system,
            temperature=body.get("temperature"),
            max_tokens=body.get("max_tokens"),
            tools=_extract_tools(body),
            tool_choice=_extract_tool_choice(body),
        )
        for message in body["messages"]:
            role = message.get("role")
            if role not in ("user", "assistant"):
                raise UnsupportedRequestError(f"unsupported role {role!r}")
            _extract_message(message, conversation.messages)
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
            "messages": _messages_to_anthropic(conversation.messages),
        }
        if conversation.tools:
            tools = []
            for tool in conversation.tools:
                entry: dict = {
                    "name": tool["name"],
                    # input_schema is required on this API; an absent neutral
                    # schema means "takes anything", which is an open object.
                    "input_schema": tool.get("parameters") or {"type": "object"},
                }
                if tool.get("description") is not None:
                    entry["description"] = tool["description"]
                tools.append(entry)
            body["tools"] = tools
        choice = conversation.tool_choice
        if choice is not None:
            if isinstance(choice, dict):
                body["tool_choice"] = {"type": "tool", "name": choice["name"]}
            else:
                body["tool_choice"] = {
                    "type": {"auto": "auto", "required": "any", "none": "none"}[choice]
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

    def normalize_usage(self, usage) -> TokenUsage:
        # Anthropic conventions: input_tokens EXCLUDES cache traffic —
        # cache_read_input_tokens / cache_creation_input_tokens are separate,
        # additive fields, so they map straight onto the disjoint buckets.
        # Thinking tokens are already inside output_tokens.
        if not isinstance(usage, dict):
            return TokenUsage()

        def as_int(key: str) -> "int | None":
            value = usage.get(key)
            return value if isinstance(value, int) else None

        return TokenUsage(
            input=as_int("input_tokens"),
            cache_read=as_int("cache_read_input_tokens"),
            cache_write=as_int("cache_creation_input_tokens"),
            output=as_int("output_tokens"),
            raw=usage,
        )

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
        tool_calls = tuple(
            ToolCall(
                name=block.get("name") or "",
                arguments=block.get("input") if block.get("input") is not None else {},
                id=block.get("id"),
            )
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        )
        return DecodedResponse(
            provider=self.name,
            model=obj.get("model"),
            text=text,
            finish_reason=obj.get("stop_reason"),
            usage=obj.get("usage"),
            streamed=False,
            tool_calls=tool_calls,
        )

    def _decode_sse(self, payload: bytes) -> DecodedResponse:
        text_parts = []
        stop_reason: Optional[str] = None
        model: Optional[str] = None
        usage: Optional[dict] = None
        saw_event = False
        # Streamed tool calls: content_block_start carries id + name, then
        # input_json_delta events stream the argument JSON in fragments.
        calls_acc: "dict[int, dict]" = {}
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
            elif event_type == "content_block_start":
                block = obj.get("content_block") or {}
                if block.get("type") == "tool_use":
                    calls_acc[obj.get("index", 0)] = {
                        "id": block.get("id"),
                        "name": block.get("name") or "",
                        "parts": [],
                    }
            elif event_type == "content_block_delta":
                delta = obj.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text", ""))
                elif delta.get("type") == "input_json_delta":
                    entry = calls_acc.get(obj.get("index", 0))
                    if entry is not None:
                        entry["parts"].append(delta.get("partial_json", ""))
            elif event_type == "message_delta":
                delta = obj.get("delta") or {}
                stop_reason = delta.get("stop_reason") or stop_reason
                if obj.get("usage"):
                    usage = {**(usage or {}), **obj["usage"]}
        if not saw_event:
            raise DecodeError("anthropic SSE stream contained no events")
        tool_calls = []
        for _, entry in sorted(calls_acc.items()):
            raw = "".join(entry["parts"])
            try:
                arguments: object = json.loads(raw) if raw.strip() else {}
            except ValueError:
                arguments = raw  # keep the unparseable fragment; never drop it
            tool_calls.append(ToolCall(name=entry["name"], arguments=arguments, id=entry["id"]))
        return DecodedResponse(
            provider=self.name,
            model=model,
            text="".join(text_parts),
            finish_reason=stop_reason,
            usage=usage,
            streamed=True,
            tool_calls=tuple(tool_calls),
        )
