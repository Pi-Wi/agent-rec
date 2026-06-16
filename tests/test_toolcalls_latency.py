"""
Tool-call translation/comparison and latency capture.

Covers the agent-shaped corpus path end to end: extracting tool definitions,
assistant tool calls and tool results into the neutral conversation,
rebuilding them for either provider dialect, decoding tool calls out of JSON
and SSE responses, scoring them with the ``toolcalls`` comparator (selection +
arguments, never execution), grouping them under one semantic key — plus the
latency provenance the transports now stamp and the report surfaces.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.comparators import ToolCallsComparator
from agentrec.keying import fingerprint
from agentrec.migration import LatencyStats, RowResult
from agentrec.providers import (
    AnthropicAdapter,
    Conversation,
    OpenAIAdapter,
    ToolCall,
    DecodedResponse,
    UnsupportedRequestError,
    decode_interaction,
    render_response,
)
from agentrec.store import InMemoryStore
from agentrec.transport import RecordingTransport, SyncRecordingTransport

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WEATHER_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}

WEATHER_TOOL_ANTHROPIC = {
    "name": "get_weather",
    "description": "Current weather for a city.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _interaction(*, url: str, request_body: dict, chunks: list, content_type: bytes) -> CapturedInteraction:
    return CapturedInteraction(
        request=CapturedRequest(
            method="POST", url=url, headers=[], content=json.dumps(request_body).encode()
        ),
        response_status=200,
        response_headers=[(b"content-type", content_type)],
        response_extensions={},
        chunks=[CapturedChunk(data=c) for c in chunks],
        metadata={},
    )


def _decoded(text: str = "", tool_calls=()) -> DecodedResponse:
    return DecodedResponse(provider="openai", model="m", text=text, tool_calls=tuple(tool_calls))


# ---------------------------------------------------------------------------
# Extraction — OpenAI dialect
# ---------------------------------------------------------------------------


def test_extract_openai_tools_and_history():
    conv = OpenAIAdapter().extract_conversation(
        {
            "model": "gpt-4o-mini",
            "tools": [WEATHER_TOOL_OPENAI],
            "tool_choice": "auto",
            "messages": [
                {"role": "user", "content": "weather in Paris?"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "18°C"},
            ],
        }
    )
    assert conv.tools == [
        {
            "name": "get_weather",
            "description": "Current weather for a city.",
            "parameters": WEATHER_TOOL_OPENAI["function"]["parameters"],
        }
    ]
    assert conv.tool_choice == "auto"
    assert conv.messages[1]["tool_calls"] == [
        {"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}}
    ]
    assert conv.messages[2] == {"role": "tool", "tool_call_id": "call_1", "content": "18°C"}


def test_extract_openai_forced_tool_choice():
    conv = OpenAIAdapter().extract_conversation(
        {
            "model": "gpt-4o-mini",
            "tools": [WEATHER_TOOL_OPENAI],
            "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert conv.tool_choice == {"name": "get_weather"}


def test_extract_openai_legacy_functions_api_still_skips():
    with pytest.raises(UnsupportedRequestError, match="legacy functions"):
        OpenAIAdapter().extract_conversation(
            {
                "messages": [{"role": "function", "name": "f", "content": "x"}],
            }
        )


# ---------------------------------------------------------------------------
# Cross-dialect translation
# ---------------------------------------------------------------------------


def _agent_conversation() -> Conversation:
    return Conversation(
        system="Be helpful.",
        messages=[
            {"role": "user", "content": "weather in Paris?"},
            {
                "role": "assistant",
                "content": "Checking.",
                "tool_calls": [
                    {"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "18°C"},
        ],
        tools=[
            {
                "name": "get_weather",
                "description": "Current weather for a city.",
                "parameters": WEATHER_TOOL_OPENAI["function"]["parameters"],
            }
        ],
        tool_choice="required",
    )


def test_build_openai_request_with_tools(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    _, _, body = OpenAIAdapter().build_request(_agent_conversation(), "gpt-4o-mini")
    assert body["tools"] == [WEATHER_TOOL_OPENAI]
    assert body["tool_choice"] == "required"
    assistant = body["messages"][2]
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"city": "Paris"}
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "call_1", "content": "18°C"}


def test_build_anthropic_request_with_tools(monkeypatch):
    """The same neutral agent step translates to the Anthropic dialect."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    _, _, body = AnthropicAdapter().build_request(_agent_conversation(), "claude-haiku-4-5")
    assert body["tools"] == [WEATHER_TOOL_ANTHROPIC]
    assert body["tool_choice"] == {"type": "any"}
    assistant = body["messages"][1]
    assert assistant["role"] == "assistant"
    assert assistant["content"][0] == {"type": "text", "text": "Checking."}
    assert assistant["content"][1] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "get_weather",
        "input": {"city": "Paris"},
    }
    # The tool result is a user-role tool_result block (alternation preserved).
    result = body["messages"][2]
    assert result["role"] == "user"
    assert result["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "call_1",
        "content": "18°C",
    }


def test_anthropic_merges_tool_results_with_following_user_text(monkeypatch):
    """Consecutive tool/user neutral messages must merge: this API requires
    strictly alternating roles."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    conv = Conversation(
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "name": "f", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            {"role": "user", "content": "now summarize"},
        ],
    )
    _, _, body = AnthropicAdapter().build_request(conv, "claude-haiku-4-5")
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["assistant", "user"]
    user_blocks = body["messages"][1]["content"]
    assert user_blocks[0]["type"] == "tool_result"
    assert user_blocks[1] == {"type": "text", "text": "now summarize"}


def test_anthropic_round_trip_through_neutral(monkeypatch):
    """Anthropic request → neutral → Anthropic request is lossless."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    adapter = AnthropicAdapter()
    original = {
        "model": "claude-haiku-4-5",
        "max_tokens": 64,
        "tools": [WEATHER_TOOL_ANTHROPIC],
        "messages": [
            {"role": "user", "content": "weather in Paris?"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "get_weather", "input": {"city": "Paris"}}
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "18°C"}],
            },
        ],
    }
    conv = adapter.extract_conversation(original)
    _, _, rebuilt = adapter.build_request(conv, "claude-haiku-4-5")
    assert rebuilt["tools"] == original["tools"]
    assert rebuilt["messages"] == original["messages"]


def test_unparseable_arguments_stay_string_and_skip_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    conv = OpenAIAdapter().extract_conversation(
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "c", "function": {"name": "f", "arguments": "{not json"}}
                    ],
                },
            ],
        }
    )
    assert conv.messages[1]["tool_calls"][0]["arguments"] == "{not json"
    with pytest.raises(UnsupportedRequestError, match="not a JSON object"):
        AnthropicAdapter().build_request(conv, "claude-haiku-4-5")


# ---------------------------------------------------------------------------
# Decoding tool calls
# ---------------------------------------------------------------------------


def test_decode_openai_json_tool_calls():
    body = {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_9",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city": "Oslo"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    interaction = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        chunks=[json.dumps(body).encode()],
        content_type=b"application/json",
    )
    decoded = decode_interaction(interaction)
    assert decoded.tool_calls == (
        ToolCall(name="get_weather", arguments={"city": "Oslo"}, id="call_9"),
    )
    assert "[tool_call] get_weather" in render_response(decoded)


def test_decode_openai_sse_tool_call_deltas():
    """Streamed tool calls: id+name first, then argument JSON in fragments."""
    def chunk(delta, finish=None):
        return {
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }

    stream = [
        chunk({"tool_calls": [{"index": 0, "id": "call_3", "function": {"name": "get_weather", "arguments": ""}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"ci'}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": 'ty": "Oslo"}'}}]}),
        chunk({}, finish="tool_calls"),
    ]
    interaction = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        chunks=[_sse(c) for c in stream] + [b"data: [DONE]\n\n"],
        content_type=b"text/event-stream",
    )
    decoded = decode_interaction(interaction)
    assert decoded.tool_calls == (
        ToolCall(name="get_weather", arguments={"city": "Oslo"}, id="call_3"),
    )
    assert decoded.finish_reason == "tool_calls"


def test_decode_anthropic_json_tool_use():
    body = {
        "model": "claude-haiku-4-5",
        "content": [
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": "toolu_7", "name": "get_weather", "input": {"city": "Oslo"}},
        ],
        "stop_reason": "tool_use",
    }
    interaction = _interaction(
        url="https://api.anthropic.com/v1/messages",
        request_body={"model": "claude-haiku-4-5", "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]},
        chunks=[json.dumps(body).encode()],
        content_type=b"application/json",
    )
    decoded = decode_interaction(interaction)
    assert decoded.text == "Checking."
    assert decoded.tool_calls == (
        ToolCall(name="get_weather", arguments={"city": "Oslo"}, id="toolu_7"),
    )


def test_decode_anthropic_sse_input_json_deltas():
    events = [
        {"type": "message_start", "message": {"model": "claude-haiku-4-5"}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_2", "name": "get_weather"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"city"'}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": ': "Oslo"}'}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
    ]
    interaction = _interaction(
        url="https://api.anthropic.com/v1/messages",
        request_body={"model": "claude-haiku-4-5", "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]},
        chunks=[_sse(e) for e in events],
        content_type=b"text/event-stream",
    )
    decoded = decode_interaction(interaction)
    assert decoded.tool_calls == (
        ToolCall(name="get_weather", arguments={"city": "Oslo"}, id="toolu_2"),
    )
    assert decoded.finish_reason == "tool_use"


# ---------------------------------------------------------------------------
# Semantic keys
# ---------------------------------------------------------------------------


def test_tool_requests_group_across_providers():
    """The same agent step recorded on either provider shares a semantic key,
    even though provider-minted call ids differ."""
    openai_fp = fingerprint(
        httpx.Request(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            content=json.dumps(
                {
                    "model": "gpt-4o-mini",
                    "tools": [WEATHER_TOOL_OPENAI],
                    "messages": [
                        {"role": "system", "content": "Be helpful."},
                        {"role": "user", "content": "weather in Paris?"},
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {"id": "call_A", "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}}
                            ],
                        },
                        {"role": "tool", "tool_call_id": "call_A", "content": "18°C"},
                    ],
                }
            ).encode(),
        )
    )
    anthropic_fp = fingerprint(
        httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            content=json.dumps(
                {
                    "model": "claude-haiku-4-5",
                    "max_tokens": 64,
                    "system": "Be helpful.",
                    "tools": [WEATHER_TOOL_ANTHROPIC],
                    "messages": [
                        {"role": "user", "content": "weather in Paris?"},
                        {
                            "role": "assistant",
                            "content": [
                                {"type": "tool_use", "id": "toolu_B", "name": "get_weather", "input": {"city": "Paris"}}
                            ],
                        },
                        {
                            "role": "user",
                            "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "18°C"}],
                        },
                    ],
                }
            ).encode(),
        )
    )
    assert openai_fp.semantic_key == anthropic_fp.semantic_key


def test_tools_change_the_semantic_key():
    """The same prompt with and without tools is a different ask."""
    def fp(body):
        return fingerprint(
            httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                content=json.dumps(body).encode(),
            )
        )

    plain = fp({"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})
    with_tools = fp(
        {
            "model": "gpt-4o-mini",
            "tools": [WEATHER_TOOL_OPENAI],
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert plain.semantic_key != with_tools.semantic_key


# ---------------------------------------------------------------------------
# toolcalls comparator
# ---------------------------------------------------------------------------


def _compare(baseline_calls, target_calls):
    return asyncio.run(
        ToolCallsComparator().compare("p", _decoded(tool_calls=baseline_calls), _decoded(tool_calls=target_calls))
    )


def test_toolcalls_match():
    result = _compare(
        [ToolCall(name="get_weather", arguments={"city": "Paris"}, id="a")],
        [ToolCall(name="get_weather", arguments={"city": "Paris"}, id="b")],  # ids differ: irrelevant
    )
    assert result.passed is True
    assert result.score == 1.0
    assert "get_weather" in result.detail


def test_toolcalls_neither_called_passes():
    result = _compare([], [])
    assert result.passed is True and result.score == 1.0


def test_toolcalls_wrong_tool_fails():
    result = _compare(
        [ToolCall(name="get_weather", arguments={})],
        [ToolCall(name="search", arguments={})],
    )
    assert result.passed is False
    assert result.score == 0.0
    assert "get_weather→search" in result.detail


def test_toolcalls_argument_diff_scores_fraction():
    result = _compare(
        [ToolCall(name="f", arguments={"a": 1, "b": 2})],
        [ToolCall(name="f", arguments={"a": 1, "b": 3})],
    )
    assert result.passed is False
    assert result.score == pytest.approx(0.5)
    assert "f.b: 2→3" in result.detail


def test_toolcalls_missing_call_fails():
    result = _compare(
        [ToolCall(name="f", arguments={}), ToolCall(name="g", arguments={})],
        [ToolCall(name="f", arguments={})],
    )
    assert result.passed is False
    assert result.score == pytest.approx(0.5)
    assert "missing in target" in result.detail


def test_toolcalls_text_only_baseline_vs_tool_calling_target_fails():
    result = asyncio.run(
        ToolCallsComparator().compare(
            "p", _decoded(text="plain answer"), _decoded(tool_calls=[ToolCall(name="f", arguments={})])
        )
    )
    assert result.passed is False
    assert "extra in target" in result.detail


# ---------------------------------------------------------------------------
# End-to-end: a tool-calling baseline migrates cross-provider
# ---------------------------------------------------------------------------


def test_migration_of_tool_calling_baseline(tmp_path, monkeypatch):
    from agentrec.comparators import build_comparators
    from agentrec.migration import run_migration
    from agentrec.store import FileStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = FileStore(tmp_path / "corpus")

    baseline_response = {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 30, "completion_tokens": 9},
    }
    baseline = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={
            "model": "gpt-4o-mini",
            "tools": [WEATHER_TOOL_OPENAI],
            "messages": [{"role": "user", "content": "weather in Paris?"}],
        },
        chunks=[json.dumps(baseline_response).encode()],
        content_type=b"application/json",
    )
    baseline.metadata["latency_s"] = 2.5

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.host == "api.anthropic.com"
        assert body["tools"] == [WEATHER_TOOL_ANTHROPIC]
        return httpx.Response(
            200,
            json={
                "model": "claude-haiku-4-5",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_X",
                        "name": "get_weather",
                        "input": {"city": "Paris"},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 25, "output_tokens": 12},
            },
        )

    async def run():
        await store.save("tooled", baseline)
        return await run_migration(
            store,
            "claude-haiku-4-5",
            build_comparators("toolcalls"),
            inner_transport=httpx.MockTransport(handler),
        )

    report = asyncio.run(run())
    row = next(r for r in report.rows if r.baseline_id == "tooled")
    assert row.status == "ok"
    comparison = row.comparisons[0]
    assert comparison.comparator == "toolcalls"
    assert comparison.passed is True
    # Tool calls are carried structured (not inlined into the prose text), so
    # the report can render them as a distinct block.
    assert [c.name for c in row.baseline_tool_calls] == ["get_weather"]
    assert [c.name for c in row.target_tool_calls] == ["get_weather"]
    assert row.baseline_tool_calls[0].arguments == {"city": "Paris"}
    assert row.baseline_latency_s == 2.5
    assert isinstance(row.target_latency_s, float)


# ---------------------------------------------------------------------------
# Latency provenance
# ---------------------------------------------------------------------------


class _OneShotTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        return httpx.Response(200, json={"ok": True})


class _SyncOneShotTransport(httpx.BaseTransport):
    def handle_request(self, request):
        return httpx.Response(200, json={"ok": True})


def test_recording_transport_stamps_latency():
    store = InMemoryStore()

    async def run():
        transport = RecordingTransport(_OneShotTransport(), store, key="x")
        client = httpx.AsyncClient(transport=transport)
        response = await client.post("https://example.com/v1/x", json={"q": 1})
        await response.aread()
        await client.aclose()

    asyncio.run(run())
    interaction = store.load_sync("x")
    assert isinstance(interaction.metadata.get("latency_s"), float)
    assert interaction.metadata["latency_s"] >= 0.0
    assert isinstance(interaction.metadata.get("latency_first_chunk_s"), float)
    assert interaction.metadata["latency_first_chunk_s"] <= interaction.metadata["latency_s"]


def test_sync_recording_transport_stamps_latency():
    store = InMemoryStore()
    with httpx.Client(transport=SyncRecordingTransport(_SyncOneShotTransport(), store, key="x")) as client:
        client.post("https://example.com/v1/x", json={"q": 1}).read()
    interaction = store.load_sync("x")
    assert isinstance(interaction.metadata.get("latency_s"), float)


def test_latency_stats_and_report_rendering():
    from agentrec.migration import MigrationReport
    from agentrec.report import render_markdown

    rows = [
        RowResult(
            semantic_key="k1",
            baseline_id="b1",
            migration_id="m1",
            prompt_preview="p1",
            baseline_text="x",
            target_text="x",
            baseline_latency_s=2.0,
            target_latency_s=1.0,
        ),
        RowResult(
            semantic_key="k2",
            baseline_id="b2",
            migration_id="m2",
            prompt_preview="p2",
            baseline_text="y",
            target_text="y",
            baseline_latency_s=4.0,
            target_latency_s=1.0,
        ),
        RowResult(  # latency unknown on one side: excluded from the stats
            semantic_key="k3",
            baseline_id="b3",
            migration_id="m3",
            prompt_preview="p3",
            baseline_latency_s=9.0,
        ),
    ]
    report = MigrationReport(
        target_model="claude-haiku-4-5",
        target_provider="anthropic",
        corpus="corpus",
        generated_at="2026-06-12T00:00:00+00:00",
        comparator_names=["exact"],
        rows=rows,
    )
    stats = report.latency_stats()
    assert stats == LatencyStats(rows=2, baseline_mean_s=3.0, target_mean_s=1.0)
    assert stats.ratio == pytest.approx(1 / 3)

    markdown = render_markdown(report)
    assert "| Latency (mean) |" in markdown  # consolidated totals table
    assert "2.00s→1.00s" in markdown  # per-row cell
    assert "9.00s→?" in markdown  # half-known latency still shown per row
