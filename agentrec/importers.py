"""
Corpus importers: turn an observability export into a migratable corpus.

The recorder is the *fast* path to a corpus, but it needs your code to route
through one httpx client — a non-starter for teams who already ship traffic to
an LLM-observability backend and don't want to touch prod for a one-off
migration question.  ``agentrec import`` reads what they already have —
Langfuse / LangSmith run exports, or OpenTelemetry GenAI spans — and writes
cassettes the migration runner consumes exactly like recorded ones.

Synthesized cassettes (the honest bit)
--------------------------------------
An exported interaction has the *prompt and the answer*, but not the original
wire bytes (no raw SSE frames, no exact request body).  So an importer
**synthesizes** a cassette: a request body and a single non-streaming JSON
response body, both in the OpenAI chat-completions dialect — the one shape
every source maps onto cleanly.  This is faithful enough for migration (the
runner re-asks the *target*; the baseline only needs a decodable conversation,
the recorded answer text, and token counts) and is marked as such:

* ``metadata["imported_from"]`` names the source (``"langfuse"`` / … ),
* ``metadata["imported"] = True`` flags the cassette as synthesized,
* ``metadata["imported_provider"]`` keeps the source's own notion of the
  provider when it reported one (the *real* baseline model id is preserved on
  the body, so reports still name the model that actually answered).

Choosing one uniform dialect is deliberate: ``semantic_key`` is derived from
the *provider-neutral* conversation, so an imported OpenAI-shaped cassette and
a natively-recorded Anthropic cassette of the same logical prompt still group
under one key — imported and recorded traffic compare side by side.

Everything is best-effort and never raises on a single bad record: a record an
importer can't understand becomes a *skipped* entry with a reason in the
returned :class:`ImportSummary`, never a crashed run.  Non-text content (images)
is dropped from the synthesized prompt — those rows would be honest skips at
migration time anyway.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest
from .keying import _sanitize, fingerprint
from .store import InteractionStore

# Synthesized cassettes always speak this dialect (see module docstring).
_SYNTH_URL = "https://api.openai.com/v1/chat/completions"
_SYNTH_PROVIDER = "openai"

IMPORT_PREFIX = "imported__"

SOURCES = ("langfuse", "langsmith", "otel")


@dataclass
class ImportedRecord:
    """One source interaction normalised toward the synthesized cassette.

    ``messages`` are already in the OpenAI request shape (role/content, with
    ``tool_calls`` on assistant messages and ``tool_call_id`` on tool ones);
    ``response_text`` and ``response_tool_calls`` are the assistant answer.
    """

    ref: str  # human-readable handle for skip reporting
    model: Optional[str] = None
    provider: Optional[str] = None  # the source's own provider label, if any
    system: Optional[str] = None
    messages: List[dict] = field(default_factory=list)
    response_text: str = ""
    response_tool_calls: List[dict] = field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None  # OpenAI-shaped (prompt_tokens/completion_tokens)
    recorded_at: Optional[str] = None
    category: Optional[str] = None
    record_id: Optional[str] = None  # stable id from the source, if present
    source: Optional[str] = None  # which importer produced this record


@dataclass
class ImportSummary:
    """Outcome of one import: the cassette ids written and what was skipped."""

    source: str
    input: str
    imported: List[str] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)  # (ref, reason)

    @property
    def imported_count(self) -> int:
        return len(self.imported)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


class ImportSourceError(ValueError):
    """A whole import failed (unreadable file, unknown/undetectable source).

    Subclasses ``ValueError`` so the CLI's usage-error handler reports it
    (exit 2), like ``PricingError``.
    """


# ---------------------------------------------------------------------------
# Shared message/content coercion
# ---------------------------------------------------------------------------

_ROLE_MAP = {
    "human": "user",
    "user": "user",
    "ai": "assistant",
    "assistant": "assistant",
    "model": "assistant",
    "system": "system",
    "developer": "system",
    "tool": "tool",
    "function": "tool",
}

# LangChain serialises messages with a class-name path; map the leaf to a role.
_LC_CLASS_ROLE = {
    "HumanMessage": "user",
    "HumanMessageChunk": "user",
    "AIMessage": "assistant",
    "AIMessageChunk": "assistant",
    "SystemMessage": "system",
    "ToolMessage": "tool",
    "FunctionMessage": "tool",
}


def _content_text(content: Any) -> str:
    """Plain text from a message content (string, or list/dict of parts).

    Non-text parts (images, audio) are dropped — an importer keeps the text it
    can use rather than failing the whole record.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if part.get("type") in (None, "text") and isinstance(part.get("text"), str):
                    parts.append(part["text"])
        return "".join(parts)
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


def _lc_role(message: dict) -> Optional[str]:
    """Role of a LangChain-serialised message, or None if it isn't one."""
    ids = message.get("id")
    if isinstance(ids, list) and ids:
        return _LC_CLASS_ROLE.get(ids[-1])
    lc_type = message.get("type")  # some dumps use a bare "human"/"ai" type tag
    if isinstance(lc_type, str):
        return _ROLE_MAP.get(lc_type)
    return None


def _coerce_message(raw: Any) -> Optional[dict]:
    """One source message → an OpenAI-shaped request message, or None to skip."""
    if isinstance(raw, str):
        return {"role": "user", "content": raw}
    if not isinstance(raw, dict):
        return None

    # LangChain serialised form: {"lc":1,"type":"constructor","id":[...],"kwargs":{...}}
    kwargs = raw.get("kwargs") if isinstance(raw.get("kwargs"), dict) else None
    lc_role = _lc_role(raw)
    if kwargs is not None and lc_role is not None:
        body = kwargs
        role = lc_role
    else:
        body = raw
        role = _ROLE_MAP.get(str(raw.get("role") or raw.get("type") or "").lower())
    if role is None:
        return None

    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": body.get("tool_call_id") or body.get("id"),
            "content": _content_text(body.get("content")),
        }

    message: dict = {"role": role, "content": _content_text(body.get("content"))}
    if role == "assistant":
        calls = _coerce_tool_calls(body.get("tool_calls"))
        if calls:
            message["tool_calls"] = calls
    return message


def _coerce_tool_calls(raw: Any) -> List[dict]:
    """OpenAI-shaped ``tool_calls`` from assorted source shapes (best-effort)."""
    if not isinstance(raw, list):
        return []
    out: List[dict] = []
    for i, call in enumerate(raw):
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = function.get("name") or call.get("name")
        if not name:
            continue
        args = function.get("arguments")
        if args is None:
            args = call.get("args") if call.get("args") is not None else {}
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        out.append(
            {
                "id": call.get("id") or f"call_{i}",
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
    return out


def _split_system(messages: List[dict]) -> Tuple[Optional[str], List[dict]]:
    """Lift leading system message(s) out into a single system string."""
    system_parts: List[str] = []
    rest: List[dict] = []
    for message in messages:
        if message["role"] == "system" and not rest:
            system_parts.append(message.get("content") or "")
        else:
            rest.append(message)
    system = "\n\n".join(p for p in system_parts if p) or None
    return system, rest


def _normalize_usage(
    input_tokens: Optional[int], output_tokens: Optional[int]
) -> Optional[dict]:
    """OpenAI-shaped usage dict, or None when the source reported no counts."""
    if input_tokens is None and output_tokens is None:
        return None
    usage: dict = {}
    if input_tokens is not None:
        usage["prompt_tokens"] = input_tokens
    if output_tokens is not None:
        usage["completion_tokens"] = output_tokens
    if input_tokens is not None and output_tokens is not None:
        usage["total_tokens"] = input_tokens + output_tokens
    return usage


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _iso(value: Any) -> Optional[str]:
    """Normalise an assortment of timestamp shapes to an ISO-8601 string.

    Accepts an already-ISO string (returned as-is), or an epoch number —
    nanoseconds (OTLP ``startTimeUnixNano``), micros, millis or seconds — and
    converts it by picking the scale that lands in a plausible date window.
    """
    if isinstance(value, str) and value:
        stripped = value.strip()
        if stripped.lstrip("-").replace(".", "", 1).isdigit():
            value = float(stripped) if "." in stripped else int(stripped)
        else:
            return value  # already an ISO-8601-ish string
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    for scale in (1e9, 1e6, 1e3, 1.0):  # nanos, micros, millis, seconds
        seconds = value / scale
        if 1e8 < seconds < 1e11:  # roughly 1973..5138 — a real timestamp
            try:
                return _dt.datetime.fromtimestamp(
                    seconds, tz=_dt.timezone.utc
                ).isoformat(timespec="seconds")
            except (ValueError, OverflowError, OSError):
                return None
    return None


# ---------------------------------------------------------------------------
# Source parsers — each yields ImportedRecords (or skip reasons via exceptions)
# ---------------------------------------------------------------------------


class _Skip(Exception):
    """One record could not be imported; the message is the reason."""


def _parse_langfuse(obj: dict) -> ImportedRecord:
    """A Langfuse generation/observation export object."""
    if isinstance(obj.get("type"), str) and obj["type"].upper() not in ("GENERATION", "LLM", ""):
        raise _Skip(f"not a generation (type={obj['type']!r})")

    raw_input = obj.get("input")
    messages: List[dict] = []
    if isinstance(raw_input, dict) and isinstance(raw_input.get("messages"), list):
        raw_messages = raw_input["messages"]
    elif isinstance(raw_input, list):
        raw_messages = raw_input
    elif isinstance(raw_input, str):
        raw_messages = [{"role": "user", "content": raw_input}]
    else:
        raise _Skip("no usable input messages")
    for raw in raw_messages:
        coerced = _coerce_message(raw)
        if coerced is not None:
            messages.append(coerced)
    if not messages:
        raise _Skip("no usable input messages")
    system, rest = _split_system(messages)
    if not rest:
        raise _Skip("input has only a system prompt")

    output = obj.get("output")
    response_text, tool_calls = _output_text_and_calls(output)

    usage = obj.get("usage") or {}
    in_tok = _as_int(usage.get("input")) if isinstance(usage, dict) else None
    out_tok = _as_int(usage.get("output")) if isinstance(usage, dict) else None
    if isinstance(usage, dict):
        in_tok = in_tok if in_tok is not None else _as_int(usage.get("promptTokens"))
        out_tok = out_tok if out_tok is not None else _as_int(usage.get("completionTokens"))

    category = None
    meta = obj.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("category"), str):
        category = meta["category"]

    return ImportedRecord(
        ref=str(obj.get("id") or obj.get("name") or "langfuse-record"),
        model=obj.get("model") or obj.get("modelName"),
        provider=obj.get("provider"),
        system=system,
        messages=rest,
        response_text=response_text,
        response_tool_calls=tool_calls,
        usage=_normalize_usage(in_tok, out_tok),
        recorded_at=_iso(obj.get("startTime") or obj.get("timestamp")),
        category=category,
        record_id=obj.get("id"),
    )


def _parse_langsmith(obj: dict) -> ImportedRecord:
    """A LangSmith ``llm`` run export object."""
    run_type = obj.get("run_type")
    if isinstance(run_type, str) and run_type not in ("llm", "chat", "chat_model", ""):
        raise _Skip(f"not an llm run (run_type={run_type!r})")

    inputs = obj.get("inputs") or {}
    raw_messages = inputs.get("messages") if isinstance(inputs, dict) else None
    # LangSmith nests a batch: inputs.messages is often [[msg, msg, ...]].
    if isinstance(raw_messages, list) and raw_messages and isinstance(raw_messages[0], list):
        raw_messages = raw_messages[0]
    if not isinstance(raw_messages, list):
        if isinstance(inputs, dict) and isinstance(inputs.get("input"), str):
            raw_messages = [{"role": "user", "content": inputs["input"]}]
        else:
            raise _Skip("no usable input messages")
    messages = [m for m in (_coerce_message(r) for r in raw_messages) if m is not None]
    if not messages:
        raise _Skip("no usable input messages")
    system, rest = _split_system(messages)
    if not rest:
        raise _Skip("input has only a system prompt")

    response_text, tool_calls = _langsmith_output(obj.get("outputs"))

    extra = obj.get("extra") if isinstance(obj.get("extra"), dict) else {}
    invocation = extra.get("invocation_params") if isinstance(extra.get("invocation_params"), dict) else {}
    model = (
        invocation.get("model")
        or invocation.get("model_name")
        or obj.get("model")
    )
    in_tok, out_tok = _langsmith_usage(obj)
    ls_metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
    provider = invocation.get("_type") or ls_metadata.get("ls_provider")

    return ImportedRecord(
        ref=str(obj.get("id") or obj.get("name") or "langsmith-run"),
        model=model,
        provider=provider,
        system=system,
        messages=rest,
        response_text=response_text,
        response_tool_calls=tool_calls,
        usage=_normalize_usage(in_tok, out_tok),
        recorded_at=_iso(obj.get("start_time") or obj.get("start_time_ms")),
        record_id=obj.get("id"),
    )


def _langsmith_output(outputs: Any) -> Tuple[str, List[dict]]:
    """Assistant text + tool calls from a LangSmith run's ``outputs``."""
    if not isinstance(outputs, dict):
        return "", []
    generations = outputs.get("generations")
    # generations is [[gen, ...]] or [gen, ...]; take the first generation.
    while isinstance(generations, list) and generations and isinstance(generations[0], list):
        generations = generations[0]
    if isinstance(generations, list) and generations:
        gen = generations[0]
        if isinstance(gen, dict):
            message = gen.get("message")
            if isinstance(message, dict):
                kwargs = message.get("kwargs") if isinstance(message.get("kwargs"), dict) else message
                text = _content_text(kwargs.get("content"))
                additional = kwargs.get("additional_kwargs")
                raw_calls = kwargs.get("tool_calls")
                if not raw_calls and isinstance(additional, dict):
                    raw_calls = additional.get("tool_calls")
                calls = _coerce_tool_calls(raw_calls)
                if text or calls:
                    return text, calls
            if isinstance(gen.get("text"), str):
                return gen["text"], []
    # Fall back to a plain {"output": "..."} shape.
    return _content_text(outputs.get("output") or outputs.get("content")), []


def _langsmith_usage(obj: dict) -> Tuple[Optional[int], Optional[int]]:
    outputs = obj.get("outputs") if isinstance(obj.get("outputs"), dict) else {}
    llm_output = outputs.get("llm_output") if isinstance(outputs.get("llm_output"), dict) else {}
    token_usage = llm_output.get("token_usage") if isinstance(llm_output.get("token_usage"), dict) else {}
    in_tok = _as_int(token_usage.get("prompt_tokens"))
    out_tok = _as_int(token_usage.get("completion_tokens"))
    if in_tok is None and out_tok is None:
        # Newer LangChain stamps usage_metadata on the message itself.
        generations = outputs.get("generations")
        while isinstance(generations, list) and generations and isinstance(generations[0], list):
            generations = generations[0]
        if isinstance(generations, list) and generations and isinstance(generations[0], dict):
            message = generations[0].get("message") or {}
            kwargs = message.get("kwargs") if isinstance(message.get("kwargs"), dict) else message
            usage_meta = kwargs.get("usage_metadata") if isinstance(kwargs, dict) else None
            if isinstance(usage_meta, dict):
                in_tok = _as_int(usage_meta.get("input_tokens"))
                out_tok = _as_int(usage_meta.get("output_tokens"))
    return in_tok, out_tok


def _output_text_and_calls(output: Any) -> Tuple[str, List[dict]]:
    """Assistant text + tool calls from a Langfuse-style ``output`` field."""
    if output is None:
        return "", []
    if isinstance(output, str):
        return output, []
    if isinstance(output, dict):
        calls = _coerce_tool_calls(output.get("tool_calls"))
        return _content_text(output.get("content")) or _content_text(output.get("text")), calls
    if isinstance(output, list):
        return _content_text(output), []
    return "", []


# --- OpenTelemetry GenAI spans ---------------------------------------------


def _otlp_value(value: Any) -> Any:
    """Unwrap one OTLP ``AnyValue`` (``{"stringValue": ...}``) to a Python value."""
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "boolValue"):
        if key in value:
            return value[key]
    for key in ("intValue", "doubleValue"):
        if key in value:
            num = value[key]
            return _as_int(num) if key == "intValue" else num
    if "arrayValue" in value:
        values = (value["arrayValue"] or {}).get("values") or []
        return [_otlp_value(v) for v in values]
    if "kvlistValue" in value:
        return {kv.get("key"): _otlp_value(kv.get("value")) for kv in (value["kvlistValue"] or {}).get("values") or []}
    return value


def _otel_attrs(span: dict) -> Dict[str, Any]:
    """Flat ``{key: value}`` attributes from a span (flat dict or OTLP list)."""
    attrs = span.get("attributes")
    if isinstance(attrs, dict):
        return attrs
    out: Dict[str, Any] = {}
    if isinstance(attrs, list):
        for item in attrs:
            if isinstance(item, dict) and "key" in item:
                out[item["key"]] = _otlp_value(item.get("value"))
    return out


def _otel_indexed_messages(attrs: Dict[str, Any], prefix: str) -> List[dict]:
    """Messages from indexed attrs: ``{prefix}.{i}.role`` / ``.content``."""
    messages: List[dict] = []
    i = 0
    while True:
        role = attrs.get(f"{prefix}.{i}.role")
        content = attrs.get(f"{prefix}.{i}.content")
        if role is None and content is None:
            break
        messages.append({"role": role or "user", "content": content})
        i += 1
    return messages


def _otel_messages_from_attr(value: Any) -> List[dict]:
    """Messages from a single attribute holding a JSON string or a list."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return [{"role": "user", "content": value}]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [m for m in value if isinstance(m, (dict, str))]
    return []


def _otel_role_messages(
    attrs: Dict[str, Any], events_attrs: Dict[str, Any], prefix: str
) -> List[dict]:
    """Messages for one gen_ai role (``gen_ai.prompt`` / ``gen_ai.completion``).

    Tries the indexed form (``{prefix}.{i}.role``) then the single-attribute
    form (a JSON string / list under ``{prefix}``), first on the span's own
    attributes and then on its merged event attributes (the older
    content-capture form) — the first non-empty result wins.
    """
    for source in (attrs, events_attrs):
        messages = _otel_indexed_messages(source, prefix)
        if messages:
            return messages
        if prefix in source:
            messages = _otel_messages_from_attr(source[prefix])
            if messages:
                return messages
    return []


def _parse_otel(span: dict) -> ImportedRecord:
    """One OpenTelemetry GenAI span (semantic-convention attributes/events)."""
    attrs = _otel_attrs(span)
    if not any(k.startswith("gen_ai.") for k in attrs):
        # Maybe the gen_ai data lives on events (older content-capture form).
        if not _otel_events(span):
            raise _Skip("span carries no gen_ai.* attributes")

    events_attrs = _otel_event_attrs(span)

    prompt_raw = _otel_role_messages(attrs, events_attrs, "gen_ai.prompt")
    messages = [m for m in (_coerce_message(r) for r in prompt_raw) if m is not None]
    if not messages:
        raise _Skip("no usable prompt messages")
    system, rest = _split_system(messages)
    if not rest:
        raise _Skip("prompt has only a system message")

    completion_raw = _otel_role_messages(attrs, events_attrs, "gen_ai.completion")
    response_text = _content_text(completion_raw[0].get("content")) if completion_raw else ""
    tool_calls = (
        _coerce_tool_calls(completion_raw[0].get("tool_calls")) if completion_raw else []
    )

    in_tok = _as_int(attrs.get("gen_ai.usage.input_tokens"))
    if in_tok is None:
        in_tok = _as_int(attrs.get("gen_ai.usage.prompt_tokens"))
    out_tok = _as_int(attrs.get("gen_ai.usage.output_tokens"))
    if out_tok is None:
        out_tok = _as_int(attrs.get("gen_ai.usage.completion_tokens"))

    return ImportedRecord(
        ref=str(span.get("name") or attrs.get("gen_ai.request.model") or "otel-span"),
        model=attrs.get("gen_ai.request.model") or attrs.get("gen_ai.response.model"),
        provider=attrs.get("gen_ai.system"),
        system=system,
        messages=rest,
        response_text=response_text,
        response_tool_calls=tool_calls,
        usage=_normalize_usage(in_tok, out_tok),
        recorded_at=_iso(span.get("startTimeUnixNano") or span.get("start_time")),
        record_id=span.get("spanId") or span.get("span_id"),
    )


def _otel_events(span: dict) -> list:
    events = span.get("events")
    return events if isinstance(events, list) else []


def _otel_event_attrs(span: dict) -> Dict[str, Any]:
    """Merge attributes across a span's events into one flat dict."""
    merged: Dict[str, Any] = {}
    for event in _otel_events(span):
        if isinstance(event, dict):
            merged.update(_otel_attrs(event))
    return merged


# ---------------------------------------------------------------------------
# Loading + detection
# ---------------------------------------------------------------------------

_PARSERS = {
    "langfuse": _parse_langfuse,
    "langsmith": _parse_langsmith,
    "otel": _parse_otel,
}


def _iter_input_records(path: Path) -> List[Any]:
    """Read a JSON / JSONL / OTLP file into a flat list of record objects."""
    text = path.read_text(encoding="utf-8")
    records: List[Any] = []
    stripped = text.lstrip()
    if path.suffix.lower() == ".jsonl" or (stripped and stripped[0] not in "[{"):
        for line in text.splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    else:
        data = json.loads(text)
        records = data if isinstance(data, list) else [data]

    # Unwrap common container shapes down to the per-record objects.
    flat: List[Any] = []
    for obj in records:
        flat.extend(_unwrap_container(obj))
    return flat


def _unwrap_container(obj: Any) -> List[Any]:
    """Pull individual records out of a wrapper object (OTLP, Langfuse, …)."""
    if not isinstance(obj, dict):
        return [obj]
    # OTLP: resourceSpans[].scopeSpans[].spans[]
    if "resourceSpans" in obj:
        spans: List[Any] = []
        for rs in obj.get("resourceSpans") or []:
            for ss in (rs or {}).get("scopeSpans") or (rs or {}).get("instrumentationLibrarySpans") or []:
                spans.extend((ss or {}).get("spans") or [])
        return spans
    # Langfuse/LangSmith API dumps wrap rows under "data".
    for key in ("data", "observations", "generations", "runs", "spans"):
        if isinstance(obj.get(key), list):
            return obj[key]
    return [obj]


def _detect_source(records: List[Any]) -> Optional[str]:
    """Best-effort source sniffing from a sample record's shape."""
    sample = next((r for r in records if isinstance(r, dict)), None)
    if sample is None:
        return None
    attrs = _otel_attrs(sample)
    if any(k.startswith("gen_ai.") for k in attrs) or "spanId" in sample or "span_id" in sample:
        return "otel"
    if "run_type" in sample or ("inputs" in sample and "outputs" in sample):
        return "langsmith"
    if "modelParameters" in sample or sample.get("type") in ("GENERATION", "generation") or "input" in sample:
        return "langfuse"
    return None


# ---------------------------------------------------------------------------
# Synthesis + public API
# ---------------------------------------------------------------------------


def _synthesize(record: ImportedRecord) -> Tuple[str, CapturedInteraction]:
    """A synthesized OpenAI-dialect cassette (id, interaction) for *record*."""
    messages: List[dict] = []
    if record.system:
        messages.append({"role": "system", "content": record.system})
    messages.extend(record.messages)
    request_body = {"model": record.model or "imported-model", "messages": messages}

    answer: dict = {"role": "assistant", "content": record.response_text or ""}
    if record.response_tool_calls:
        answer["tool_calls"] = record.response_tool_calls
    response_body: dict = {
        "model": record.model,
        "object": "chat.completion",
        "choices": [
            {"index": 0, "message": answer, "finish_reason": record.finish_reason or "stop"}
        ],
    }
    if record.usage:
        response_body["usage"] = record.usage

    request_content = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = CapturedRequest(
        method="POST",
        url=_SYNTH_URL,
        headers=[(b"content-type", b"application/json")],
        content=request_content,
    )
    fp = fingerprint(httpx.Request("POST", _SYNTH_URL, content=request_content))

    metadata: Dict[str, Any] = {
        "provider": _SYNTH_PROVIDER,
        "model": record.model,
        "semantic_key": fp.semantic_key,
        "imported": True,
        "imported_from": record.source,
    }
    if record.recorded_at:
        metadata["recorded_at"] = record.recorded_at
    if record.provider:
        metadata["imported_provider"] = record.provider
    if record.category:
        metadata["category"] = record.category

    # The single JSON document is one chunk — the replay/decode source of truth.
    interaction = CapturedInteraction(
        request=request,
        response_status=200,
        response_headers=[(b"content-type", b"application/json")],
        response_extensions={},
        chunks=[CapturedChunk(data=json.dumps(response_body, ensure_ascii=False).encode("utf-8"))],
        metadata=metadata,
    )

    if record.record_id:
        cid = f"{IMPORT_PREFIX}{record.source}__{_sanitize(str(record.record_id))}"
    else:
        cid = f"{IMPORT_PREFIX}{record.source}__{fp.cassette_id[-16:]}"
    return cid, interaction


async def import_corpus(
    input_path: str | Path,
    store: InteractionStore,
    *,
    source: str = "auto",
    category: Optional[str] = None,
) -> ImportSummary:
    """Import an observability export into *store* as synthesized cassettes.

    *source* is one of :data:`SOURCES` or ``"auto"`` (sniff the shape).
    *category* tags every imported row when the source carried none — so a
    whole export can land under one report category.  Returns an
    :class:`ImportSummary`; a single unparseable record is skipped (with a
    reason), never fatal.
    """
    path = Path(input_path)
    try:
        records = _iter_input_records(path)
    except (OSError, ValueError) as exc:
        raise ImportSourceError(f"could not read {path}: {exc}") from None

    if source == "auto":
        detected = _detect_source(records)
        if detected is None:
            raise ImportSourceError(
                "could not detect the export format; pass --source "
                f"({'|'.join(SOURCES)})"
            )
        source = detected
    if source not in _PARSERS:
        raise ImportSourceError(f"unknown source {source!r} (expected {', '.join(SOURCES)})")

    parser = _PARSERS[source]
    summary = ImportSummary(source=source, input=str(path))
    for index, raw in enumerate(records):
        ref = f"record[{index}]"
        try:
            if not isinstance(raw, dict):
                raise _Skip("record is not a JSON object")
            record = parser(raw)
            record.source = source
            if category and not record.category:
                record.category = category
            ref = record.ref
            cid, interaction = _synthesize(record)
        except _Skip as exc:
            summary.skipped.append((ref, str(exc)))
            continue
        except Exception as exc:  # never let one malformed record kill the run
            summary.skipped.append((ref, f"unexpected: {exc}"))
            continue
        await store.save(cid, interaction)
        summary.imported.append(cid)
    return summary
