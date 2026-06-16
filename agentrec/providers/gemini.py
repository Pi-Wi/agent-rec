"""
Google Gemini adapter (``generativelanguage.googleapis.com`` ``generateContent``).

Gemini is the third migration dialect: OpenAI ↔ Anthropic ↔ Gemini is the
triangle teams actually evaluate.  This adapter translates the
``generateContent`` REST shape both ways and decodes its responses (one JSON
document, or an ``alt=sse`` stream).

Dialect specifics encoded here:

* messages live under ``contents`` with roles ``user`` / ``model`` (no system
  role — the system prompt is a top-level ``systemInstruction``); each turn is
  a list of ``parts``;
* tools are ``[{"functionDeclarations": [{"name","description","parameters"}]}]``;
  an assistant tool call is a ``functionCall`` part, a tool result is a
  ``functionResponse`` part on a ``user`` turn;
* sampling/limits live under ``generationConfig`` (``maxOutputTokens``,
  ``temperature``, ``responseMimeType`` for native JSON mode);
* ``usageMetadata`` reports ``promptTokenCount`` (inclusive of cached),
  ``candidatesTokenCount`` (output), ``cachedContentTokenCount`` and
  ``thoughtsTokenCount`` (a reasoning subset of output).

Honest skips mirror the other adapters: non-text parts (``inlineData`` /
``fileData`` — images, audio) raise :class:`UnsupportedRequestError`, as do
tool-call arguments that never parsed to an object (Gemini ``args`` must be a
struct, same constraint as Anthropic ``tool_use.input``).

NOTE: the core paths — non-streaming and streaming (SSE) decoding, request
building, usage normalisation and tool calls — are verified against the live
``generateContent`` API by ``tests/test_live_gemini.py`` (skips without a key;
last run against ``gemini-2.5-flash``).  A couple of build-side translations
(tool-result ``functionResponse``, JSON mode) are still only offline-tested.
The Gemini Python SDK does not route through httpx, so live *recording* is not
available; seed a corpus by importing Gemini traffic via ``agentrec import``
and/or use Gemini as a migration *target*.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

from .base import (
    Conversation,
    DecodedResponse,
    DecodeError,
    MissingAPIKeyError,
    ProviderAdapter,
    TokenUsage,
    ToolCall,
    UnsupportedRequestError,
    sse_data_lines,
)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Native JSON mode: Gemini honours generationConfig.responseMimeType, so the
# neutral "caller asked for a JSON object" re-emits natively (no prompt nudge).
_JSON_MIME = "application/json"

_CHOICE_TO_MODE = {"auto": "AUTO", "required": "ANY", "none": "NONE"}
_MODE_TO_CHOICE = {"AUTO": "auto", "ANY": "required", "NONE": "none"}


def _parts_text(parts: object, *, what: str) -> str:
    """Concatenated text of ``parts``; raises on a non-text (image/audio) part."""
    if not isinstance(parts, list):
        raise UnsupportedRequestError(f"unsupported {what} shape: {type(parts).__name__}")
    out: List[str] = []
    for part in parts:
        if not isinstance(part, dict):
            raise UnsupportedRequestError(f"unsupported {what} part")
        if "text" in part:
            out.append(part.get("text") or "")
        else:
            kind = next((k for k in part if k != "text"), "unknown")
            raise UnsupportedRequestError(f"non-text {what} part {kind!r}")
    return "".join(out)


class GeminiAdapter(ProviderAdapter):
    name = "gemini"
    host_patterns = ("generativelanguage",)
    model_patterns = ("gemini-", "gemini")
    api_key_env = "GEMINI_API_KEY"

    def api_key(self) -> str:
        # Google's tooling accepts either name; honour both before failing.
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise MissingAPIKeyError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set; a live call to "
                "gemini needs it (recorded auth headers are redacted)."
            )
        return key

    # --- request → neutral conversation -----------------------------------

    def extract_conversation(self, body: dict) -> Conversation:
        if not isinstance(body, dict) or not isinstance(body.get("contents"), list):
            raise UnsupportedRequestError("request body has no contents list")

        system = None
        system_instruction = body.get("systemInstruction") or body.get("system_instruction")
        if isinstance(system_instruction, dict):
            system = _parts_text(system_instruction.get("parts"), what="system")
        elif isinstance(system_instruction, str):
            system = system_instruction

        generation_config = body.get("generationConfig") or body.get("generation_config") or {}
        response_format = None
        if generation_config.get("responseMimeType") == _JSON_MIME or generation_config.get(
            "response_mime_type"
        ) == _JSON_MIME:
            response_format = {"type": "json_object"}

        conversation = Conversation(
            system=system,
            temperature=generation_config.get("temperature"),
            max_tokens=generation_config.get("maxOutputTokens")
            or generation_config.get("max_output_tokens"),
            response_format=response_format,
            tools=_extract_tools(body),
            tool_choice=_extract_tool_choice(body),
        )
        for content in body["contents"]:
            self._extract_content(content, conversation.messages)
        if not conversation.messages:
            raise UnsupportedRequestError("conversation has no user/model messages")
        return conversation

    def _extract_content(self, content: dict, out: List[dict]) -> None:
        """Append the neutral message(s) for one Gemini ``contents`` entry."""
        if not isinstance(content, dict):
            raise UnsupportedRequestError("content entry is not an object")
        role = content.get("role") or "user"
        parts = content.get("parts")
        if not isinstance(parts, list):
            raise UnsupportedRequestError("content entry has no parts list")

        text_parts: List[str] = []
        tool_calls: List[dict] = []
        for part in parts:
            if not isinstance(part, dict):
                raise UnsupportedRequestError("unsupported content part")
            if "text" in part:
                text_parts.append(part.get("text") or "")
            elif "functionCall" in part or "function_call" in part:
                call = part.get("functionCall") or part.get("function_call") or {}
                tool_calls.append(
                    {
                        "id": None,  # Gemini does not mint call ids
                        "name": call.get("name"),
                        "arguments": call.get("args") if call.get("args") is not None else {},
                    }
                )
            elif "functionResponse" in part or "function_response" in part:
                resp = part.get("functionResponse") or part.get("function_response") or {}
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": resp.get("name"),  # Gemini keys results by tool name
                        "content": _function_response_text(resp.get("response")),
                    }
                )
            else:
                kind = next((k for k in part if k not in ("text",)), "unknown")
                raise UnsupportedRequestError(f"non-text content part {kind!r}")

        text = "".join(text_parts)
        neutral_role = "assistant" if role == "model" else "user"
        if tool_calls:
            out.append({"role": "assistant", "content": text, "tool_calls": tool_calls})
        elif text or not (out and out[-1].get("role") == "tool"):
            out.append({"role": neutral_role, "content": text})

    # --- neutral conversation → request ------------------------------------

    def build_request(
        self,
        conversation: Conversation,
        model: str,
        *,
        max_tokens_default: int = 4096,
        stream: bool = False,
    ) -> Tuple[str, Dict[str, str], dict]:
        contents = _messages_to_contents(conversation.messages)
        body: dict = {"contents": contents}

        if conversation.system:
            body["systemInstruction"] = {"parts": [{"text": conversation.system}]}
        if conversation.tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        _tool_declaration(tool) for tool in conversation.tools
                    ]
                }
            ]
        choice = conversation.tool_choice
        if choice is not None:
            if isinstance(choice, dict):
                body["toolConfig"] = {
                    "functionCallingConfig": {
                        "mode": "ANY",
                        "allowedFunctionNames": [choice["name"]],
                    }
                }
            else:
                body["toolConfig"] = {"functionCallingConfig": {"mode": _CHOICE_TO_MODE[choice]}}

        generation_config: dict = {}
        # max_output_tokens is optional on this API: only carry over a cap the
        # baseline actually set; never invent one.
        if conversation.max_tokens is not None:
            generation_config["maxOutputTokens"] = conversation.max_tokens
        if conversation.temperature is not None:
            generation_config["temperature"] = conversation.temperature
        if conversation.response_format is not None:
            generation_config["responseMimeType"] = _JSON_MIME
        if generation_config:
            body["generationConfig"] = generation_config

        # Streaming is a different endpoint (and ?alt=sse asks for the SSE wire
        # form the decoder reads, not the default chunked-JSON-array form).
        if stream:
            url = f"{_API_BASE}/{model}:streamGenerateContent?alt=sse"
        else:
            url = f"{_API_BASE}/{model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key(),
            "Content-Type": "application/json",
        }
        return url, headers, body

    # --- usage normalisation -----------------------------------------------

    def normalize_usage(self, usage) -> TokenUsage:
        # Gemini conventions: promptTokenCount INCLUDES cachedContentTokenCount
        # (so subtract for the uncached bucket); candidatesTokenCount is output;
        # thoughtsTokenCount is a reasoning subset of output (informational).
        if not isinstance(usage, dict):
            return TokenUsage()

        def as_int(*keys: str) -> "int | None":
            for key in keys:
                value = usage.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    return value
            return None

        prompt = as_int("promptTokenCount", "prompt_token_count")
        cached = as_int("cachedContentTokenCount", "cached_content_token_count")
        uncached = prompt
        if prompt is not None and cached is not None:
            uncached = max(0, prompt - cached)
        return TokenUsage(
            input=uncached,
            cache_read=cached,
            output=as_int("candidatesTokenCount", "candidates_token_count"),
            reasoning=as_int("thoughtsTokenCount", "thoughts_token_count"),
            raw=usage,
        )

    # --- response decoding -------------------------------------------------

    def decode_response(self, payload: bytes, *, is_sse: bool) -> DecodedResponse:
        if is_sse:
            return self._decode_sse(payload)
        try:
            obj = json.loads(payload)
        except ValueError as exc:
            raise DecodeError(f"gemini response is not valid JSON: {exc}") from None
        candidates = obj.get("candidates") or []
        if not candidates:
            raise DecodeError("gemini response has no candidates")
        candidate = candidates[0]
        text, tool_calls = _decode_parts((candidate.get("content") or {}).get("parts") or [])
        return DecodedResponse(
            provider=self.name,
            model=obj.get("modelVersion") or obj.get("model"),
            text=text,
            finish_reason=candidate.get("finishReason"),
            usage=obj.get("usageMetadata"),
            streamed=False,
            tool_calls=tool_calls,
        )

    def _decode_sse(self, payload: bytes) -> DecodedResponse:
        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        finish_reason: Optional[str] = None
        model: Optional[str] = None
        usage: Optional[dict] = None
        saw_chunk = False
        for data in sse_data_lines(payload):
            if data.strip() in ("", "[DONE]"):
                continue
            try:
                obj = json.loads(data)
            except ValueError as exc:
                raise DecodeError(f"malformed gemini SSE frame: {exc}") from None
            saw_chunk = True
            model = obj.get("modelVersion") or obj.get("model") or model
            if obj.get("usageMetadata"):
                usage = obj["usageMetadata"]
            for candidate in obj.get("candidates") or []:
                chunk_text, chunk_calls = _decode_parts(
                    (candidate.get("content") or {}).get("parts") or []
                )
                if chunk_text:
                    text_parts.append(chunk_text)
                tool_calls.extend(chunk_calls)
                finish_reason = candidate.get("finishReason") or finish_reason
        if not saw_chunk:
            raise DecodeError("gemini SSE stream contained no chunks")
        return DecodedResponse(
            provider=self.name,
            model=model,
            text="".join(text_parts),
            finish_reason=finish_reason,
            usage=usage,
            streamed=True,
            tool_calls=tuple(tool_calls),
        )


def _function_response_text(response: object) -> str:
    """Plain text from a Gemini ``functionResponse.response`` payload."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        # The common convention wraps the tool's return under a single key.
        for key in ("content", "result", "output"):
            value = response.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(response, ensure_ascii=False)
    return "" if response is None else json.dumps(response, ensure_ascii=False)


def _extract_tools(body: dict) -> "list[dict] | None":
    """Neutral tool definitions from a Gemini ``tools`` array."""
    raw_tools = body.get("tools")
    if not raw_tools:
        return None
    tools: List[dict] = []
    for entry in raw_tools:
        if not isinstance(entry, dict):
            raise UnsupportedRequestError("unsupported tool entry")
        declarations = entry.get("functionDeclarations") or entry.get("function_declarations")
        if declarations is None:
            # Server-side tools (googleSearch, codeExecution, …) execute on
            # Google's infrastructure and have no cross-provider neutral form.
            kind = next((k for k in entry), "unknown")
            raise UnsupportedRequestError(f"unsupported tool type {kind!r}")
        for declaration in declarations:
            if not isinstance(declaration, dict) or not declaration.get("name"):
                raise UnsupportedRequestError("tool declaration has no name")
            tool = {"name": declaration["name"]}
            if declaration.get("description") is not None:
                tool["description"] = declaration["description"]
            if declaration.get("parameters") is not None:
                tool["parameters"] = declaration["parameters"]
            tools.append(tool)
    return tools


def _extract_tool_choice(body: dict) -> object:
    """Neutral tool_choice from a Gemini ``toolConfig``."""
    config = body.get("toolConfig") or body.get("tool_config")
    if not isinstance(config, dict):
        return None
    fcc = config.get("functionCallingConfig") or config.get("function_calling_config") or {}
    mode = (fcc.get("mode") or "").upper()
    allowed = fcc.get("allowedFunctionNames") or fcc.get("allowed_function_names")
    if mode == "ANY" and isinstance(allowed, list) and len(allowed) == 1:
        return {"name": allowed[0]}
    if mode in _MODE_TO_CHOICE:
        return _MODE_TO_CHOICE[mode]
    if not mode:
        return None
    raise UnsupportedRequestError(f"unsupported tool_choice mode {mode!r}")


def _tool_declaration(tool: dict) -> dict:
    declaration: dict = {"name": tool["name"]}
    if tool.get("description") is not None:
        declaration["description"] = tool["description"]
    if tool.get("parameters") is not None:
        declaration["parameters"] = tool["parameters"]
    return declaration


def _messages_to_contents(messages: List[dict]) -> List[dict]:
    """Gemini ``contents`` from neutral messages.

    Gemini uses ``user`` / ``model`` roles; neutral ``tool`` results become
    ``functionResponse`` parts on a ``user`` turn.  Consecutive same-role
    turns are merged (the API rejects a trailing-role mismatch less strictly
    than Anthropic, but merging keeps the transcript clean and unambiguous).
    """
    out: List[dict] = []
    # Gemini links a functionResponse to its functionCall by *name*, not by a
    # call id (it mints none), so map ids back to names as calls go by.
    id_to_name: Dict[str, str] = {}

    def emit(role: str, parts: List[dict]) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["parts"].extend(parts)
        else:
            out.append({"role": role, "parts": parts})

    for message in messages:
        role = message.get("role")
        if role == "tool":
            call_id = message.get("tool_call_id")
            name = id_to_name.get(call_id) or call_id or "tool"
            emit(
                "user",
                [
                    {
                        "functionResponse": {
                            "name": name,
                            "response": {"content": message.get("content") or ""},
                        }
                    }
                ],
            )
        elif message.get("tool_calls"):
            parts: List[dict] = []
            if message.get("content"):
                parts.append({"text": message["content"]})
            for call in message["tool_calls"]:
                if call.get("id") and call.get("name"):
                    id_to_name[call["id"]] = call["name"]
                arguments = call.get("arguments")
                if arguments is not None and not isinstance(arguments, dict):
                    # functionCall.args must be a struct; a string here means
                    # the recorded argument JSON never parsed.
                    raise UnsupportedRequestError(
                        "assistant tool-call arguments are not a JSON object"
                    )
                parts.append(
                    {
                        "functionCall": {
                            "name": call.get("name"),
                            "args": arguments if arguments is not None else {},
                        }
                    }
                )
            emit("model", parts)
        else:
            neutral_role = "model" if role == "assistant" else "user"
            emit(neutral_role, [{"text": message.get("content") or ""}])
    return out


def _decode_parts(parts: list) -> Tuple[str, Tuple[ToolCall, ...]]:
    """Assistant text + tool calls from a response candidate's ``parts``."""
    text_parts: List[str] = []
    tool_calls: List[ToolCall] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if "text" in part:
            text_parts.append(part.get("text") or "")
        elif "functionCall" in part or "function_call" in part:
            call = part.get("functionCall") or part.get("function_call") or {}
            tool_calls.append(
                ToolCall(
                    name=call.get("name") or "",
                    arguments=call.get("args") if call.get("args") is not None else {},
                    id=None,
                )
            )
    return "".join(text_parts), tuple(tool_calls)
