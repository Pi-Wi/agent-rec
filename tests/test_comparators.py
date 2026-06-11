"""
Comparator tests: the offline metrics in pure logic, the API-backed metrics
(embedding, judge) against httpx.MockTransport, and the --compare spec parser.
"""
from __future__ import annotations

import json

import httpx
import pytest

from agentrec.comparators import (
    EmbeddingComparator,
    ExactMatchComparator,
    FuzzyComparator,
    JudgeComparator,
    build_comparators,
    cosine_similarity,
)
from agentrec.providers import DecodedResponse


def _resp(text: str, provider: str = "openai") -> DecodedResponse:
    return DecodedResponse(provider=provider, model="m", text=text)


# ---------------------------------------------------------------------------
# Offline comparators
# ---------------------------------------------------------------------------


async def test_exact_normalizes_whitespace_and_case():
    result = await ExactMatchComparator().compare("p", _resp("  Positive\n"), _resp("positive"))
    assert result.passed is True and result.score == 1.0

    result = await ExactMatchComparator().compare("p", _resp("positive"), _resp("negative"))
    assert result.passed is False and result.score == 0.0


async def test_fuzzy_threshold():
    comparator = FuzzyComparator(threshold=0.8)
    near = await comparator.compare("p", _resp("the quick brown fox"), _resp("the quick brown foxes"))
    assert near.passed is True and near.score > 0.8

    far = await comparator.compare("p", _resp("yes"), _resp("completely different answer"))
    assert far.passed is False and far.score < 0.5


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# API-backed comparators (mocked transport)
# ---------------------------------------------------------------------------


async def test_embedding_comparator(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0]},
                    {"index": 1, "embedding": [1.0, 0.0]},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await EmbeddingComparator(http).compare("p", _resp("a"), _resp("b"))
    assert result.passed is True
    assert result.score == pytest.approx(1.0)


async def test_judge_comparator_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["headers"] = dict(request.headers)
        verdict = '{"equivalent": true, "score": 0.92, "reason": "same label"}'
        return httpx.Response(
            200,
            json={
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": f"Here you go: {verdict}"}],
                "stop_reason": "end_turn",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await JudgeComparator(http, judge_model="claude-opus-4-8").compare(
            "Classify this.", _resp("positive"), _resp("Positive!")
        )

    assert result.passed is True
    assert result.score == pytest.approx(0.92)
    assert result.detail == "same label"
    # The judge request must not carry sampling params (newest models 400 on them).
    assert "temperature" not in seen["body"] and "top_p" not in seen["body"]
    assert seen["body"]["max_tokens"] == 1024
    assert seen["headers"]["x-api-key"] == "test-key"


async def test_judge_lenient_parse_failure_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "claude-opus-4-8", "content": [{"type": "text", "text": "no json here"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError, match="no JSON object"):
            await JudgeComparator(http).compare("p", _resp("a"), _resp("b"))
    # The migration runner catches this and degrades it to an errored result.


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def test_build_comparators_spec():
    names = [c.name for c in build_comparators("exact, judge")]
    assert names == ["exact", "judge"]

    names = [c.name for c in build_comparators("all")]
    assert names == ["exact", "fuzzy", "embedding", "judge"]

    with pytest.raises(ValueError, match="unknown comparator"):
        build_comparators("exact,levenshtein")
    with pytest.raises(ValueError, match="no comparators"):
        build_comparators(" , ")
