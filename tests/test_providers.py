"""
Provider adapter tests: decoding recorded responses (4 paths: provider x
SSE/JSON), conversation extraction/translation in both directions, and the
registry that makes providers pluggable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.providers import (
    AnthropicAdapter,
    Conversation,
    MissingAPIKeyError,
    MistralAdapter,
    OpenAIAdapter,
    UnsupportedRequestError,
    adapter_for_host,
    adapter_for_model,
    adapter_for_provider,
    build_summary,
    conversation_of,
    decode_interaction,
    usage_of,
)
from agentrec.store import FileStore

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _interaction(
    *, url: str, request_body: dict, chunks: list, content_type: bytes, metadata: dict | None = None
) -> CapturedInteraction:
    return CapturedInteraction(
        request=CapturedRequest(
            method="POST", url=url, headers=[], content=json.dumps(request_body).encode()
        ),
        response_status=200,
        response_headers=[(b"content-type", content_type)],
        response_extensions={},
        chunks=[CapturedChunk(data=c) for c in chunks],
        metadata=metadata or {},
    )


def _openai_chunk(content=None, finish=None) -> dict:
    delta = {"content": content} if content is not None else {}
    return {
        "id": "chatcmpl-x",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


# ---------------------------------------------------------------------------
# Decoding — OpenAI
# ---------------------------------------------------------------------------


def test_decode_openai_sse_with_midframe_chunk_split():
    """Chunks may split an SSE frame mid-JSON; decode must join first."""
    stream = b"".join(
        [
            _sse(_openai_chunk("Hel")),
            _sse(_openai_chunk("lo")),
            _sse(_openai_chunk(None, finish="stop")),
            b"data: [DONE]\n\n",
        ]
    )
    # Split at deliberately hostile boundaries (inside JSON tokens).
    cut1, cut2 = 17, len(stream) - 23
    chunks = [stream[:cut1], stream[cut1:cut2], stream[cut2:]]
    interaction = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        chunks=chunks,
        content_type=b"text/event-stream; charset=utf-8",
    )
    decoded = decode_interaction(interaction)
    assert decoded.text == "Hello"
    assert decoded.finish_reason == "stop"
    assert decoded.provider == "openai"
    assert decoded.streamed is True
    assert decoded.model == "gpt-4o-mini"


def test_decode_gzip_encoded_json():
    """A gzip Content-Encoding (what OpenAI actually sends) is decompressed."""
    import gzip

    body = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Billing"}, "finish_reason": "stop"}],
    }
    interaction = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "classify"}]},
        chunks=[gzip.compress(json.dumps(body).encode())],
        content_type=b"application/json",
    )
    interaction.response_headers.append((b"content-encoding", b"gzip"))
    decoded = decode_interaction(interaction)
    assert decoded.text == "Billing"


def test_decode_deflate_encoded_json():
    """zlib deflate Content-Encoding is also handled."""
    import zlib

    body = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    }
    interaction = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        chunks=[zlib.compress(json.dumps(body).encode())],
        content_type=b"application/json",
    )
    interaction.response_headers.append((b"content-encoding", b"deflate"))
    assert decode_interaction(interaction).text == "ok"


def test_decode_openai_json():
    body = {
        "model": "gpt-4o-2024-08-06",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "blue"}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 10},
    }
    interaction = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        chunks=[json.dumps(body).encode()],
        content_type=b"application/json",
    )
    decoded = decode_interaction(interaction)
    assert decoded.text == "blue"
    assert decoded.usage == {"total_tokens": 10}
    assert decoded.streamed is False


# ---------------------------------------------------------------------------
# Decoding — Anthropic
# ---------------------------------------------------------------------------


def test_decode_anthropic_sse():
    events = [
        {"type": "message_start", "message": {"model": "claude-haiku-4-5", "usage": {"input_tokens": 9}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 4}},
        {"type": "message_stop"},
    ]
    interaction = _interaction(
        url="https://api.anthropic.com/v1/messages",
        request_body={"model": "claude-haiku-4-5", "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]},
        chunks=[_sse(event) for event in events],
        content_type=b"text/event-stream",
    )
    decoded = decode_interaction(interaction)
    assert decoded.text == "Hello"
    assert decoded.finish_reason == "end_turn"
    assert decoded.model == "claude-haiku-4-5"
    assert decoded.usage == {"input_tokens": 9, "output_tokens": 4}


def test_decode_anthropic_json():
    body = {
        "model": "claude-haiku-4-5",
        "content": [{"type": "text", "text": "Positive"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 3, "output_tokens": 2},
    }
    interaction = _interaction(
        url="https://api.anthropic.com/v1/messages",
        request_body={"model": "claude-haiku-4-5", "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]},
        chunks=[json.dumps(body).encode()],
        content_type=b"application/json",
    )
    decoded = decode_interaction(interaction)
    assert decoded.text == "Positive"
    assert decoded.finish_reason == "end_turn"


def test_decode_real_corpus_cassettes():
    """Every cassette shipped in the repo corpus must decode to non-empty text."""
    if not CORPUS.is_dir():
        pytest.skip("repo corpus directory not present")
    store = FileStore(CORPUS)
    ids = [iid for iid in store.ids() if not iid.startswith("migration__")]
    if not ids:
        # FileStore() creates the directory as a side effect, so an earlier
        # run leaves an empty corpus/ behind — that's not a failure.
        pytest.skip("no cassettes in repo corpus")
    import asyncio

    async def check() -> None:
        for iid in ids:
            decoded = decode_interaction(await store.load(iid))
            assert decoded.text.strip(), f"empty decode for {iid}"

    asyncio.run(check())


# ---------------------------------------------------------------------------
# Conversation extraction & request building
# ---------------------------------------------------------------------------


def test_extract_openai_conversation_lifts_system():
    adapter = OpenAIAdapter()
    conv = adapter.extract_conversation(
        {
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "max_tokens": 100,
            "messages": [
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": [{"type": "text", "text": "Classify: good"}]},
                {"role": "assistant", "content": "positive"},
                {"role": "user", "content": "Classify: bad"},
            ],
        }
    )
    assert conv.system == "Be terse."
    assert conv.temperature == 0.2
    assert conv.max_tokens == 100
    assert [m["role"] for m in conv.messages] == ["user", "assistant", "user"]
    assert conv.messages[0]["content"] == "Classify: good"


def test_extract_openai_rejects_images_and_malformed_tools():
    adapter = OpenAIAdapter()
    # Tools are supported now, but a definition without a name is still a
    # clearly-reasoned skip, not a silent pass-through.
    with pytest.raises(UnsupportedRequestError):
        adapter.extract_conversation(
            {"messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function"}]}
        )
    with pytest.raises(UnsupportedRequestError):
        adapter.extract_conversation(
            {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {}}]}]}
        )


def test_extract_anthropic_tool_result_blocks_become_tool_messages():
    adapter = AnthropicAdapter()
    conv = adapter.extract_conversation(
        {
            "model": "claude-haiku-4-5",
            "max_tokens": 64,
            "messages": [
                {"role": "user", "content": "weather in Paris?"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me check."},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "get_weather",
                            "input": {"city": "Paris"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "18°C"}
                    ],
                },
            ],
        }
    )
    assert [m["role"] for m in conv.messages] == ["user", "assistant", "tool"]
    assert conv.messages[1]["content"] == "Let me check."
    assert conv.messages[1]["tool_calls"] == [
        {"id": "toolu_1", "name": "get_weather", "arguments": {"city": "Paris"}}
    ]
    assert conv.messages[2] == {"role": "tool", "tool_call_id": "toolu_1", "content": "18°C"}


def test_build_anthropic_request_cross_provider(monkeypatch):
    """OpenAI-recorded conversation rebuilt as an Anthropic Messages request."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    conv = Conversation(system="Be terse.", messages=[{"role": "user", "content": "hi"}])
    url, headers, body = AnthropicAdapter().build_request(conv, "claude-haiku-4-5")
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "test-anthropic-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["model"] == "claude-haiku-4-5"
    assert body["max_tokens"] == 4096  # required field injected from default
    assert body["system"] == "Be terse."
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert "stream" not in body and "temperature" not in body


def test_build_openai_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    conv = Conversation(
        system="Be terse.", messages=[{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=64
    )
    url, headers, body = OpenAIAdapter().build_request(conv, "gpt-4o-mini")
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-openai-key"
    assert body["messages"][0] == {"role": "system", "content": "Be terse."}
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 64
    assert "stream" not in body


def test_extract_openai_response_format_json_object_is_captured():
    adapter = OpenAIAdapter()
    conv = adapter.extract_conversation(
        {
            "model": "gpt-4o-mini",
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": "Triage this ticket."}],
        }
    )
    assert conv.response_format == {"type": "json_object"}

    # type "text" is the default — nothing to carry.
    conv = adapter.extract_conversation(
        {
            "model": "gpt-4o-mini",
            "response_format": {"type": "text"},
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert conv.response_format is None


def test_extract_openai_rejects_json_schema_response_format():
    adapter = OpenAIAdapter()
    with pytest.raises(UnsupportedRequestError, match="json_schema"):
        adapter.extract_conversation(
            {
                "model": "gpt-4o-mini",
                "response_format": {"type": "json_schema", "json_schema": {"name": "t"}},
                "messages": [{"role": "user", "content": "hi"}],
            }
        )


def test_build_openai_request_reemits_json_mode(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    conv = Conversation(
        messages=[{"role": "user", "content": "hi"}], response_format={"type": "json_object"}
    )
    _, _, body = OpenAIAdapter().build_request(conv, "gpt-4o")
    assert body["response_format"] == {"type": "json_object"}

    conv = Conversation(messages=[{"role": "user", "content": "hi"}])
    _, _, body = OpenAIAdapter().build_request(conv, "gpt-4o")
    assert "response_format" not in body


def test_build_anthropic_request_emulates_json_mode(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    conv = Conversation(
        system="Be terse.",
        messages=[{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )
    _, _, body = AnthropicAdapter().build_request(conv, "claude-haiku-4-5")
    assert body["system"].startswith("Be terse.")
    assert "single JSON object" in body["system"]
    assert "response_format" not in body
    assert conv.system == "Be terse."  # the shared Conversation was not mutated

    # Without a recorded system prompt, the suffix becomes the system prompt.
    conv = Conversation(
        messages=[{"role": "user", "content": "hi"}], response_format={"type": "json_object"}
    )
    _, _, body = AnthropicAdapter().build_request(conv, "claude-haiku-4-5")
    assert "single JSON object" in body["system"]

    # And no JSON mode means no synthetic system prompt at all.
    conv = Conversation(messages=[{"role": "user", "content": "hi"}])
    _, _, body = AnthropicAdapter().build_request(conv, "claude-haiku-4-5")
    assert "system" not in body


def test_response_format_does_not_change_semantic_key():
    """JSON mode is a format knob: same prompt, with and without, must group."""
    import httpx

    from agentrec.keying import fingerprint

    def fp(body: dict):
        return fingerprint(
            httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                content=json.dumps(body).encode(),
            )
        )

    plain = fp({"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Triage."}]})
    json_mode = fp(
        {
            "model": "gpt-4o-mini",
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": "Triage."}],
        }
    )
    assert plain.semantic_key == json_mode.semantic_key
    # Record/replay still distinguishes the two concrete requests.
    assert plain.cassette_id != json_mode.cassette_id


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    conv = Conversation(messages=[{"role": "user", "content": "hi"}])
    with pytest.raises(MissingAPIKeyError, match="ANTHROPIC_API_KEY"):
        AnthropicAdapter().build_request(conv, "claude-haiku-4-5")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_resolution():
    assert adapter_for_model("gpt-4o-mini").name == "openai"
    assert adapter_for_model("claude-haiku-4-5").name == "anthropic"
    assert adapter_for_model("mistral-large-latest").name == "mistral"
    assert adapter_for_model("open-mistral-nemo").name == "mistral"
    assert adapter_for_model("magistral-medium-latest").name == "mistral"
    assert adapter_for_provider("ANTHROPIC").name == "anthropic"
    assert adapter_for_provider("Mistral").name == "mistral"
    assert adapter_for_host("api.openai.com").name == "openai"
    assert adapter_for_host("api.mistral.ai").name == "mistral"
    assert adapter_for_host("example.com") is None
    with pytest.raises(LookupError):
        adapter_for_model("mystery-model-9000")


# ---------------------------------------------------------------------------
# Mistral (the OpenAI chat-completions dialect with three narrow deltas)
# ---------------------------------------------------------------------------


def test_decode_mistral_json_routes_by_host():
    """A Mistral response is OpenAI-shaped; routing is by the mistral.ai host."""
    body = {
        "model": "mistral-large-latest",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "bonjour"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    interaction = _interaction(
        url="https://api.mistral.ai/v1/chat/completions",
        request_body={"model": "mistral-large-latest", "messages": [{"role": "user", "content": "hi"}]},
        chunks=[json.dumps(body).encode()],
        content_type=b"application/json",
    )
    decoded = decode_interaction(interaction)
    assert decoded.provider == "mistral"
    assert decoded.text == "bonjour"
    # prompt_tokens/completion_tokens normalise onto the disjoint buckets.
    usage = usage_of(decoded)
    assert usage.input == 5 and usage.output == 2


def test_mistral_tool_choice_any_round_trips_through_neutral_required(monkeypatch):
    adapter = MistralAdapter()
    # Mistral spells "force a tool call" as "any"; it maps to the neutral
    # "required" the other dialects share.
    conv = adapter.extract_conversation(
        {
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": "weather?"}],
            "tools": [{"type": "function", "function": {"name": "get_weather"}}],
            "tool_choice": "any",
        }
    )
    assert conv.tool_choice == "required"

    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    _, headers, body = adapter.build_request(conv, "mistral-large-latest")
    # ... and it goes back out on the wire as "any", not "required".
    assert body["tool_choice"] == "any"
    assert headers["Authorization"] == "Bearer test-mistral-key"


def test_mistral_build_request_uses_max_tokens_even_for_reasoning_model(monkeypatch):
    """No Mistral model has the o-series max_completion_tokens quirk (Magistral included)."""
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    conv = Conversation(messages=[{"role": "user", "content": "think"}], max_tokens=64, temperature=0.3)
    url, _, body = MistralAdapter().build_request(conv, "magistral-medium-latest")
    assert url == "https://api.mistral.ai/v1/chat/completions"
    assert body["max_tokens"] == 64
    assert "max_completion_tokens" not in body
    assert body["temperature"] == 0.3  # sampling params are not dropped


def test_mistral_remaps_tool_call_ids_to_nine_char_form(monkeypatch):
    """Mistral rejects ids that are not ^[a-zA-Z0-9]{9}$; build must remap them,
    keeping an assistant call and its tool result on the same id."""
    import re

    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    valid = re.compile(r"^[a-zA-Z0-9]{9}$")

    # A recorded cross-provider (Anthropic-style) id, too long for Mistral.
    conv = Conversation(
        messages=[
            {"role": "user", "content": "weather?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "toolu_01ABCDEFGHIJKLMNOP", "name": "get_weather", "arguments": {"city": "Paris"}}
                ],
            },
            {"role": "tool", "tool_call_id": "toolu_01ABCDEFGHIJKLMNOP", "content": "18C"},
        ]
    )
    _, _, body = MistralAdapter().build_request(conv, "mistral-large-latest")
    call_id = body["messages"][1]["tool_calls"][0]["id"]
    result_id = body["messages"][2]["tool_call_id"]
    assert valid.match(call_id)
    assert call_id == result_id  # linkage preserved under the remap

    # Hand-built conversation with NO ids: synthesized, then remapped — still
    # a valid 9-char id shared by the call and its result.
    conv = Conversation(
        messages=[
            {"role": "assistant", "content": "", "tool_calls": [{"name": "f", "arguments": {}}]},
            {"role": "tool", "content": "done"},
        ]
    )
    _, _, body = MistralAdapter().build_request(conv, "mistral-small-latest")
    call_id = body["messages"][0]["tool_calls"][0]["id"]
    result_id = body["messages"][1]["tool_call_id"]
    assert valid.match(call_id)
    assert call_id == result_id


def test_mistral_keeps_already_valid_nine_char_id(monkeypatch):
    """A Mistral-recorded id (already 9 alphanumerics) is passed through as-is."""
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    conv = Conversation(
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "aB3dE6gH9", "name": "f", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "aB3dE6gH9", "content": "ok"},
        ]
    )
    _, _, body = MistralAdapter().build_request(conv, "mistral-large-latest")
    assert body["messages"][0]["tool_calls"][0]["id"] == "aB3dE6gH9"


# ---------------------------------------------------------------------------
# Interaction helpers
# ---------------------------------------------------------------------------


def test_conversation_of_and_summary():
    interaction = _interaction(
        url="https://api.openai.com/v1/chat/completions",
        request_body={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "Say hello."}],
        },
        chunks=[_sse(_openai_chunk("Hello")), b"data: [DONE]\n\n"],
        content_type=b"text/event-stream",
    )
    conv = conversation_of(interaction)
    assert conv.messages == [{"role": "user", "content": "Say hello."}]

    summary = build_summary(interaction)
    assert summary["prompt"] == "Say hello."
    assert summary["response"] == "Hello"
    assert summary["provider"] == "openai"
    assert summary["model"] == "gpt-4o-mini"
    assert summary["semantic_key"]  # recomputed despite empty metadata
