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
    OpenAIAdapter,
    UnsupportedRequestError,
    adapter_for_host,
    adapter_for_model,
    adapter_for_provider,
    build_summary,
    conversation_of,
    decode_interaction,
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


def test_extract_openai_rejects_tools_and_images():
    adapter = OpenAIAdapter()
    with pytest.raises(UnsupportedRequestError):
        adapter.extract_conversation(
            {"messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function"}]}
        )
    with pytest.raises(UnsupportedRequestError):
        adapter.extract_conversation(
            {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {}}]}]}
        )


def test_extract_anthropic_rejects_tool_blocks():
    adapter = AnthropicAdapter()
    with pytest.raises(UnsupportedRequestError):
        adapter.extract_conversation(
            {
                "model": "claude-haiku-4-5",
                "max_tokens": 64,
                "messages": [
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x"}]}
                ],
            }
        )


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
    assert adapter_for_provider("ANTHROPIC").name == "anthropic"
    assert adapter_for_host("api.openai.com").name == "openai"
    assert adapter_for_host("example.com") is None
    with pytest.raises(LookupError):
        adapter_for_model("mystery-model-9000")


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
