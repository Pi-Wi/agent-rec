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
    JsonComparator,
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


JSON_BARE = '{"category": "billing", "priority": "high"}'
JSON_FENCED = f'```json\n{JSON_BARE}\n```'


async def test_exact_ignores_whole_payload_code_fence():
    # Fenced vs bare: the fence is presentation, not content.
    result = await ExactMatchComparator().compare("p", _resp(JSON_BARE), _resp(JSON_FENCED))
    assert result.passed is True and result.score == 1.0

    # Fenced-with-language vs fenced-without.
    result = await ExactMatchComparator().compare(
        "p", _resp(f"```\n{JSON_BARE}\n```"), _resp(JSON_FENCED)
    )
    assert result.passed is True


async def test_fuzzy_ignores_whole_payload_code_fence():
    result = await FuzzyComparator().compare("p", _resp(JSON_BARE), _resp(JSON_FENCED))
    assert result.score == pytest.approx(1.0)


async def test_inner_or_partial_fences_are_content_not_wrapping():
    # An inner fence inside prose must not be stripped: these texts differ.
    inner = "Use ```json\n{}\n``` for the payload, then explain."
    result = await ExactMatchComparator().compare("p", _resp(inner), _resp("{}"))
    assert result.passed is False

    # A trailing-only fence (no opener) is not a wrapping fence either.
    trailing = '{"a": 1}\n```'
    result = await ExactMatchComparator().compare("p", _resp(trailing), _resp('{"a": 1}'))
    assert result.passed is False


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# json comparator
# ---------------------------------------------------------------------------


async def test_json_matches_despite_key_order_whitespace_and_fences():
    baseline = _resp('{"category": "billing", "priority": "high", "ok": true}')
    target = _resp('```json\n{\n  "priority": "High",\n  "ok": true,\n  "category": "billing"\n}\n```')
    result = await JsonComparator().compare("p", baseline, target)
    assert result.passed is True
    assert result.score == 1.0
    assert "all 3 fields match" in result.detail


async def test_json_partial_match_scores_fraction_with_readable_diff():
    baseline = _resp('{"category": "billing", "priority": "high", "summary": "Refund the invoice."}')
    target = _resp('{"category": "billing", "priority": "medium", "summary": "Refund the invoice."}')
    result = await JsonComparator().compare("p", baseline, target)
    assert result.passed is False
    assert result.score == pytest.approx(2 / 3)
    assert "priority: high→medium" in result.detail


async def test_json_missing_and_extra_keys_count_as_mismatches():
    baseline = _resp('{"category": "bug", "priority": "low"}')
    target = _resp('{"category": "bug", "confidence": 0.9}')
    result = await JsonComparator().compare("p", baseline, target)
    assert result.passed is False
    assert result.score == pytest.approx(1 / 3)  # category of {category, priority, confidence}
    assert "missing in target: priority" in result.detail
    assert "extra in target: confidence" in result.detail


async def test_json_nested_objects_and_arrays_compare_recursively():
    baseline = _resp('{"labels": ["a", "b"], "meta": {"source": "web", "spam": false}}')
    same = _resp('{"meta": {"spam": false, "source": "WEB"}, "labels": ["a", "b"]}')
    result = await JsonComparator().compare("p", baseline, same)
    assert result.passed is True

    flipped = _resp('{"labels": ["a", "c"], "meta": {"source": "web", "spam": false}}')
    result = await JsonComparator().compare("p", baseline, flipped)
    assert result.passed is False
    assert result.score == pytest.approx(3 / 4)
    assert "labels[1]: b→c" in result.detail


async def test_json_bool_does_not_match_number_or_string():
    result = await JsonComparator().compare("p", _resp('{"ok": true}'), _resp('{"ok": 1}'))
    assert result.passed is False
    result = await JsonComparator().compare("p", _resp('{"n": 1}'), _resp('{"n": 1.0}'))
    assert result.passed is True  # plain numeric equality


async def test_json_unparseable_target_is_a_failure_not_an_error():
    result = await JsonComparator().compare("p", _resp('{"a": 1}'), _resp("Sorry, I cannot."))
    assert result.error is False
    assert result.passed is False and result.score == 0.0
    assert "target is not valid JSON" in result.detail


async def test_json_unparseable_baseline_is_a_comparator_error():
    result = await JsonComparator().compare("p", _resp("free-form prose"), _resp('{"a": 1}'))
    assert result.error is True
    assert result.passed is None
    assert "baseline is not valid JSON" in result.detail


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

    names = [c.name for c in build_comparators("json")]
    assert names == ["json"]

    names = [c.name for c in build_comparators("all")]
    assert names == ["exact", "fuzzy", "json", "embedding", "judge"]

    with pytest.raises(ValueError, match="unknown comparator"):
        build_comparators("exact,levenshtein")
    with pytest.raises(ValueError, match="no comparators"):
        build_comparators(" , ")
