"""
Gemini adapter tests, fully offline.

Cover the third dialect's four jobs — conversation extraction, request
building, response decoding (JSON + SSE), usage normalisation — plus the
registry lookups and an end-to-end cross-provider migration (OpenAI baseline →
mock Gemini target).  The dialect is implemented from the published REST
contract; these prove the translation is self-consistent without a live call.
"""
from __future__ import annotations

import json

import httpx
import pytest

from agentrec import FileStore, build_comparators, run_migration
from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.providers import (
    Conversation,
    GeminiAdapter,
    MissingAPIKeyError,
    UnsupportedRequestError,
    adapter_for_host,
    adapter_for_model,
    conversation_of,
    decode_interaction,
)

GEMINI = GeminiAdapter()


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def test_registry_resolves_gemini_by_model_and_host():
    assert adapter_for_model("gemini-2.0-flash").name == "gemini"
    assert adapter_for_model("gemini-1.5-pro").name == "gemini"
    assert adapter_for_host("generativelanguage.googleapis.com").name == "gemini"
    # The other dialects are still distinct.
    assert adapter_for_model("gpt-4o-mini").name == "openai"
    assert adapter_for_model("claude-haiku-4-5").name == "anthropic"


# ---------------------------------------------------------------------------
# extract_conversation
# ---------------------------------------------------------------------------


def test_extract_conversation_text_system_and_config():
    body = {
        "systemInstruction": {"parts": [{"text": "You are terse."}]},
        "contents": [
            {"role": "user", "parts": [{"text": "Hello"}]},
            {"role": "model", "parts": [{"text": "Hi."}]},
            {"role": "user", "parts": [{"text": "Bye"}]},
        ],
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 256,
                             "responseMimeType": "application/json"},
    }
    conversation = GEMINI.extract_conversation(body)
    assert conversation.system == "You are terse."
    assert [(m["role"], m["content"]) for m in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "Hi."),
        ("user", "Bye"),
    ]
    assert conversation.temperature == 0.5
    assert conversation.max_tokens == 256
    assert conversation.response_format == {"type": "json_object"}


def test_extract_conversation_tools_and_function_call_and_result():
    body = {
        "contents": [
            {"role": "user", "parts": [{"text": "weather in paris?"}]},
            {"role": "model", "parts": [{"functionCall": {"name": "get_weather",
                                                          "args": {"city": "Paris"}}}]},
            {"role": "user", "parts": [{"functionResponse": {"name": "get_weather",
                                                            "response": {"content": "18C"}}}]},
        ],
        "tools": [{"functionDeclarations": [
            {"name": "get_weather", "description": "lookup",
             "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}
        ]}],
        "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
    }
    conversation = GEMINI.extract_conversation(body)
    assert conversation.tools == [
        {"name": "get_weather", "description": "lookup",
         "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}
    ]
    assert conversation.tool_choice == "required"  # ANY -> required
    assistant = conversation.messages[1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["name"] == "get_weather"
    assert assistant["tool_calls"][0]["arguments"] == {"city": "Paris"}
    tool_result = conversation.messages[2]
    assert tool_result["role"] == "tool" and tool_result["content"] == "18C"


def test_extract_tool_choice_forced_single_function():
    body = {
        "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        "toolConfig": {"functionCallingConfig": {"mode": "ANY",
                                                 "allowedFunctionNames": ["only_this"]}},
    }
    assert GEMINI.extract_conversation(body).tool_choice == {"name": "only_this"}


def test_extract_image_part_is_unsupported():
    body = {"contents": [{"role": "user", "parts": [
        {"text": "what is this?"},
        {"inlineData": {"mimeType": "image/png", "data": "AAAA"}},
    ]}]}
    with pytest.raises(UnsupportedRequestError):
        GEMINI.extract_conversation(body)


# ---------------------------------------------------------------------------
# build_request
# ---------------------------------------------------------------------------


def test_build_request_text_and_system(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    conversation = Conversation(
        system="be brief",
        messages=[{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}],
        temperature=0.3, max_tokens=128, response_format={"type": "json_object"},
    )
    url, headers, body = GEMINI.build_request(conversation, "gemini-2.0-flash")
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    assert headers["x-goog-api-key"] == "k"
    assert body["systemInstruction"] == {"parts": [{"text": "be brief"}]}
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "Hello"}]},
        {"role": "model", "parts": [{"text": "Hi"}]},
    ]
    assert body["generationConfig"]["maxOutputTokens"] == 128
    assert body["generationConfig"]["temperature"] == 0.3
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_build_request_google_api_key_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    _, headers, _ = GEMINI.build_request(
        Conversation(messages=[{"role": "user", "content": "hi"}]), "gemini-1.5-pro"
    )
    assert headers["x-goog-api-key"] == "g"


def test_build_request_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError):
        GEMINI.build_request(
            Conversation(messages=[{"role": "user", "content": "hi"}]), "gemini-1.5-pro"
        )


def test_build_request_tool_calls_and_results_roundtrip(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    conversation = Conversation(
        messages=[
            {"role": "user", "content": "weather?"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "c1", "name": "get_weather", "arguments": {"city": "Paris"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "18C"},
        ],
        tools=[{"name": "get_weather", "parameters": {"type": "object"}}],
        tool_choice={"name": "get_weather"},
    )
    _, _, body = GEMINI.build_request(conversation, "gemini-2.0-flash")
    assert body["tools"] == [{"functionDeclarations": [
        {"name": "get_weather", "parameters": {"type": "object"}}
    ]}]
    assert body["toolConfig"] == {"functionCallingConfig": {
        "mode": "ANY", "allowedFunctionNames": ["get_weather"]}}
    # model turn carries the functionCall, the following user turn its response.
    model_turn = body["contents"][1]
    assert model_turn["role"] == "model"
    assert model_turn["parts"][0]["functionCall"] == {"name": "get_weather", "args": {"city": "Paris"}}
    result_turn = body["contents"][2]
    assert result_turn["role"] == "user"
    assert result_turn["parts"][0]["functionResponse"]["name"] == "get_weather"


def test_build_request_unparseable_tool_args_is_unsupported(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    conversation = Conversation(
        messages=[{"role": "assistant", "content": "",
                   "tool_calls": [{"name": "f", "arguments": "not-json-object"}]}],
    )
    with pytest.raises(UnsupportedRequestError):
        GEMINI.build_request(conversation, "gemini-2.0-flash")


# ---------------------------------------------------------------------------
# decode_response
# ---------------------------------------------------------------------------


def test_decode_json_text_and_tool_call_and_usage():
    payload = json.dumps({
        "modelVersion": "gemini-2.0-flash",
        "candidates": [{
            "content": {"role": "model", "parts": [
                {"text": "It is sunny. "},
                {"functionCall": {"name": "alert", "args": {"level": 2}}},
            ]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 4,
                          "cachedContentTokenCount": 3, "thoughtsTokenCount": 1},
    }).encode()
    decoded = GEMINI.decode_response(payload, is_sse=False)
    assert decoded.text == "It is sunny. "
    assert decoded.model == "gemini-2.0-flash"
    assert decoded.finish_reason == "STOP"
    assert decoded.tool_calls[0].name == "alert"
    assert decoded.tool_calls[0].arguments == {"level": 2}

    usage = GEMINI.normalize_usage(decoded.usage)
    assert usage.cache_read == 3
    assert usage.input == 8  # 11 prompt - 3 cached
    assert usage.output == 4
    assert usage.reasoning == 1
    assert usage.prompt_total == 11  # input + cache_read


def test_decode_sse_accumulates_text_and_usage():
    stream = b"".join([
        _sse({"candidates": [{"content": {"parts": [{"text": "Hel"}]}}], "modelVersion": "gemini-2.0-flash"}),
        _sse({"candidates": [{"content": {"parts": [{"text": "lo"}]}, "finishReason": "STOP"}],
              "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1}}),
    ])
    # Split mid-frame to prove the join-before-parse contract holds.
    cut = 20
    decoded = GEMINI.decode_response(stream[:cut] + stream[cut:], is_sse=True)
    assert decoded.text == "Hello"
    assert decoded.streamed is True
    assert decoded.finish_reason == "STOP"
    assert GEMINI.normalize_usage(decoded.usage).output == 1


def test_decode_interaction_resolves_gemini_by_host():
    """A recorded Gemini cassette decodes via host resolution + provider tag."""
    body = {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
    response = {"candidates": [{"content": {"parts": [{"text": "hey"}]}, "finishReason": "STOP"}]}
    interaction = CapturedInteraction(
        request=CapturedRequest(
            method="POST",
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            headers=[], content=json.dumps(body).encode(),
        ),
        response_status=200,
        response_headers=[(b"content-type", b"application/json")],
        response_extensions={},
        chunks=[CapturedChunk(data=json.dumps(response).encode())],
        metadata={},
    )
    decoded = decode_interaction(interaction)
    assert decoded.provider == "gemini" and decoded.text == "hey"
    assert conversation_of(interaction).messages[0]["content"] == "hi"


# ---------------------------------------------------------------------------
# end-to-end: OpenAI baseline migrated to a mock Gemini target
# ---------------------------------------------------------------------------


def _openai_baseline(prompt: str = "name the sky color in one word") -> CapturedInteraction:
    body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
    response = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "blue"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 1},
    }
    return CapturedInteraction(
        request=CapturedRequest(
            method="POST", url="https://api.openai.com/v1/chat/completions",
            headers=[(b"content-type", b"application/json")], content=json.dumps(body).encode(),
        ),
        response_status=200,
        response_headers=[(b"content-type", b"application/json")],
        response_extensions={},
        chunks=[CapturedChunk(data=json.dumps(response).encode())],
        metadata={},
    )


def _gemini_target(text: str = "Blue") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "generativelanguage.googleapis.com"
        # The runner streams its target calls: Gemini's stream endpoint, asking
        # for the SSE wire form.  A JSON answer still decodes (by content-type).
        assert request.url.path.endswith(":streamGenerateContent")
        assert request.url.params.get("alt") == "sse"
        body = json.loads(request.content)
        assert "contents" in body
        return httpx.Response(200, json={
            "modelVersion": "gemini-2.0-flash",
            "candidates": [{"content": {"role": "model", "parts": [{"text": text}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 2, "totalTokenCount": 11},
        })
    return httpx.MockTransport(handler)


async def test_migration_openai_baseline_to_gemini_target(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    store = FileStore(tmp_path / "corpus")
    await store.save("sky", _openai_baseline())

    report = await run_migration(
        store, "gemini-2.0-flash", build_comparators("exact,fuzzy"),
        inner_transport=_gemini_target("Blue"),
    )
    row = report.rows[0]
    assert row.status == "ok"
    assert row.target_model == "gemini-2.0-flash"
    assert row.baseline_text == "blue" and row.target_text == "Blue"
    assert (row.target_in_tokens, row.target_out_tokens) == (9, 2)
    exact = next(c for c in row.comparisons if c.comparator == "exact")
    assert exact.passed is True  # "blue" == "Blue" after normalization
    assert report.target_provider == "gemini"
    assert report.all_passed
