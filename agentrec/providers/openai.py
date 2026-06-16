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
    TokenUsage,
    ToolCall,
    UnsupportedRequestError,
    sse_data_lines,
)

# Request-body fields that cannot be translated faithfully; their presence
# makes the whole request unsupported rather than silently changing its
# meaning.  ``tools``/``tool_choice`` are supported (captured into the neutral
# Conversation); the *legacy* functions API is not — modern recordings don't
# use it.  ``response_format`` is NOT here: ``{"type": "json_object"}`` is
# captured as the neutral ``Conversation.response_format``.  The
# ``json_schema`` variant stays unsupported — strict structured output can't
# be faithfully emulated on providers without it, and a prompt nudge does not
# enforce a schema.
_UNSUPPORTED_FIELDS = ("functions", "function_call")


def _parse_arguments(raw: object) -> object:
    """Parsed tool-call arguments: dict when the JSON parses, raw otherwise."""
    if not isinstance(raw, str):
        return raw if raw is not None else {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return raw  # keep the unparseable string; never invent or drop content


def _extract_tools(body: dict) -> "list[dict] | None":
    """Neutral tool definitions from an OpenAI ``tools`` array."""
    raw_tools = body.get("tools")
    if not raw_tools:
        return None
    tools = []
    for entry in raw_tools:
        if not (isinstance(entry, dict) and entry.get("type") == "function"):
            kind = entry.get("type") if isinstance(entry, dict) else entry
            raise UnsupportedRequestError(f"unsupported tool type {kind!r}")
        function = entry.get("function") or {}
        if not function.get("name"):
            raise UnsupportedRequestError("tool definition has no function name")
        tool = {"name": function["name"]}
        if function.get("description") is not None:
            tool["description"] = function["description"]
        if function.get("parameters") is not None:
            tool["parameters"] = function["parameters"]
        tools.append(tool)
    return tools


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

    # --- dialect variation points ------------------------------------------
    # Mistral speaks this exact chat-completions dialect with three narrow
    # deltas; ``MistralAdapter`` subclasses this adapter and overrides only the
    # hooks below.  For OpenAI they are no-ops, so its built requests and
    # extracted conversations are byte-for-byte unchanged.

    #: Wire spelling of "force a tool call": OpenAI "required", Mistral "any".
    #: Used in both directions (extract reads it, build emits it).
    _required_tool_choice = "required"

    def _is_reasoning_model(self, model: str) -> bool:
        """o-series models reject ``max_tokens`` and sampling params.

        Subclasses whose models have no such quirk override this to ``False``.
        """
        return model.startswith(("o1", "o3", "o4"))

    def _wire_call_id(self, call_id: str) -> str:
        """Adapt a neutral tool-call id to this dialect's id rules.

        Identity for OpenAI; Mistral remaps to its required 9-char form.  It
        must stay a pure function of *call_id* so an assistant call and its
        matching tool result keep the same id.
        """
        return call_id

    def _stream_body_fields(self) -> dict:
        """Body fields that turn a request into a streaming one for this dialect.

        OpenAI omits ``usage`` from a stream unless asked, so it adds
        ``stream_options: {"include_usage": True}`` to keep the migration
        report's token columns populated for streamed targets.  Mistral streams
        usage by default and rejects ``stream_options``, so it overrides this.
        """
        return {"stream": True, "stream_options": {"include_usage": True}}

    def _extract_tool_choice(self, body: dict) -> object:
        """Neutral ``tool_choice`` from the wire body."""
        raw = body.get("tool_choice")
        if raw is None or raw in ("auto", "none"):
            return raw
        if raw == self._required_tool_choice:
            return "required"
        if isinstance(raw, dict) and raw.get("type") == "function":
            name = (raw.get("function") or {}).get("name")
            if name:
                return {"name": name}
        raise UnsupportedRequestError(f"unsupported tool_choice {raw!r}")

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
            tools=_extract_tools(body),
            tool_choice=self._extract_tool_choice(body),
        )
        for message in body["messages"]:
            role = message.get("role")
            if role == "function":
                raise UnsupportedRequestError("request uses the legacy functions API")
            if role == "tool":
                conversation.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id"),
                        "content": _content_to_text(message.get("content")),
                    }
                )
                continue
            content = message.get("content")
            text = _content_to_text(content) if content is not None else ""
            if role in ("system", "developer"):
                if conversation.messages:
                    raise UnsupportedRequestError("system message after conversation start")
                conversation.system = (
                    text if conversation.system is None else conversation.system + "\n\n" + text
                )
            elif role == "assistant" and message.get("tool_calls"):
                calls = []
                for raw_call in message["tool_calls"]:
                    function = (raw_call or {}).get("function") or {}
                    if not function.get("name"):
                        raise UnsupportedRequestError("assistant tool call has no name")
                    calls.append(
                        {
                            "id": raw_call.get("id"),
                            "name": function["name"],
                            "arguments": _parse_arguments(function.get("arguments")),
                        }
                    )
                conversation.messages.append(
                    {"role": "assistant", "content": text, "tool_calls": calls}
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
        stream: bool = False,
    ) -> Tuple[str, Dict[str, str], dict]:
        messages: list = []
        if conversation.system:
            messages.append({"role": "system", "content": conversation.system})
        # Recorded conversations always carry call ids (both dialects require
        # them on the wire).  Hand-built ones may not: synthesize ids in call
        # order and hand them to id-less tool results in the same order, so
        # the call/result linkage the API requires still holds.
        synthesized_ids: list = []
        synthesized_count = 0
        for message in conversation.messages:
            role = message.get("role")
            if role == "tool":
                call_id = message.get("tool_call_id")
                if not call_id:
                    call_id = synthesized_ids.pop(0) if synthesized_ids else "call_0"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": self._wire_call_id(call_id),
                        "content": message.get("content") or "",
                    }
                )
            elif message.get("tool_calls"):
                out_calls = []
                for call in message["tool_calls"]:
                    call_id = call.get("id")
                    if not call_id:
                        call_id = f"call_{synthesized_count}"
                        synthesized_count += 1
                        synthesized_ids.append(call_id)
                    arguments = call.get("arguments")
                    out_calls.append(
                        {
                            "id": self._wire_call_id(call_id),
                            "type": "function",
                            "function": {
                                "name": call.get("name"),
                                "arguments": (
                                    arguments
                                    if isinstance(arguments, str)
                                    else json.dumps(arguments if arguments is not None else {})
                                ),
                            },
                        }
                    )
                out: dict = {"role": "assistant", "tool_calls": out_calls}
                if message.get("content"):
                    out["content"] = message["content"]
                messages.append(out)
            else:
                messages.append({"role": role, "content": message.get("content")})
        body: dict = {"model": model, "messages": messages}
        if conversation.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        key: tool[key]
                        for key in ("name", "description", "parameters")
                        if key in tool
                    },
                }
                for tool in conversation.tools
            ]
        choice = conversation.tool_choice
        if choice is not None:
            if isinstance(choice, dict):
                body["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
            else:
                # Neutral "required" takes this dialect's spelling ("any" on Mistral).
                body["tool_choice"] = (
                    self._required_tool_choice if choice == "required" else choice
                )
        # o-series reasoning models reject max_tokens (use max_completion_tokens
        # instead) and 400 on sampling params like temperature.
        reasoning = self._is_reasoning_model(model)
        # max_tokens is optional on this API: only carry it over when the
        # baseline set it; never invent a cap the original call didn't have.
        if conversation.max_tokens is not None:
            body["max_completion_tokens" if reasoning else "max_tokens"] = conversation.max_tokens
        if conversation.temperature is not None and not reasoning:
            body["temperature"] = conversation.temperature
        if conversation.response_format is not None:
            # Native JSON mode: re-emit on this provider's own dialect.
            body["response_format"] = {"type": "json_object"}
        if stream:
            body.update(self._stream_body_fields())
        headers = {
            "Authorization": f"Bearer {self.api_key()}",
            "Content-Type": "application/json",
        }
        return self.chat_url, headers, body

    def normalize_usage(self, usage) -> TokenUsage:
        # OpenAI conventions: prompt_tokens INCLUDES cached tokens
        # (prompt_tokens_details.cached_tokens) and completion_tokens INCLUDES
        # reasoning tokens (completion_tokens_details.reasoning_tokens) — so
        # the disjoint buckets are prompt-cached and completion as-is.
        if not isinstance(usage, dict):
            return TokenUsage()

        def as_int(value) -> "int | None":
            return value if isinstance(value, int) else None

        prompt = as_int(usage.get("prompt_tokens"))
        prompt_details = usage.get("prompt_tokens_details")
        cached = as_int(prompt_details.get("cached_tokens")) if isinstance(prompt_details, dict) else None
        completion_details = usage.get("completion_tokens_details")
        reasoning = (
            as_int(completion_details.get("reasoning_tokens"))
            if isinstance(completion_details, dict)
            else None
        )
        uncached = prompt
        if prompt is not None and cached is not None:
            uncached = max(0, prompt - cached)
        return TokenUsage(
            input=uncached,
            cache_read=cached,
            output=as_int(usage.get("completion_tokens")),
            reasoning=reasoning,
            raw=usage,
        )

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
        tool_calls = tuple(
            ToolCall(
                name=(call.get("function") or {}).get("name") or "",
                arguments=_parse_arguments((call.get("function") or {}).get("arguments")),
                id=call.get("id"),
            )
            for call in message.get("tool_calls") or ()
        )
        return DecodedResponse(
            provider=self.name,
            model=obj.get("model"),
            text=message.get("content") or "",
            finish_reason=choices[0].get("finish_reason"),
            usage=obj.get("usage"),
            streamed=False,
            tool_calls=tool_calls,
        )

    def _decode_sse(self, payload: bytes) -> DecodedResponse:
        text_parts = []
        finish_reason: Optional[str] = None
        model: Optional[str] = None
        usage: Optional[dict] = None
        saw_chunk = False
        # Streamed tool calls arrive as deltas keyed by index: the id and name
        # in the first delta, the argument JSON in string fragments after.
        calls_acc: "dict[int, dict]" = {}
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
                for call_delta in delta.get("tool_calls") or ():
                    index = call_delta.get("index", 0)
                    entry = calls_acc.setdefault(index, {"id": None, "name": "", "parts": []})
                    if call_delta.get("id"):
                        entry["id"] = call_delta["id"]
                    function = call_delta.get("function") or {}
                    if function.get("name"):
                        entry["name"] += function["name"]
                    if function.get("arguments"):
                        entry["parts"].append(function["arguments"])
                finish_reason = choices[0].get("finish_reason") or finish_reason
        if not saw_chunk:
            raise DecodeError("openai SSE stream contained no chunks")
        tool_calls = tuple(
            ToolCall(
                name=entry["name"],
                arguments=_parse_arguments("".join(entry["parts"])),
                id=entry["id"],
            )
            for _, entry in sorted(calls_acc.items())
        )
        return DecodedResponse(
            provider=self.name,
            model=model,
            text="".join(text_parts),
            finish_reason=finish_reason,
            usage=usage,
            streamed=True,
            tool_calls=tool_calls,
        )
