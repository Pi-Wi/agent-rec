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
# json comparator — field scope
# ---------------------------------------------------------------------------


async def test_json_scoped_fields_drive_verdict_free_text_is_informational():
    baseline = _resp('{"category": "billing", "priority": "high", "summary": "Refund the invoice."}')
    target = _resp('{"category": "billing", "priority": "high", "summary": "Issue a refund."}')
    result = await JsonComparator(fields=["category", "priority"]).compare("p", baseline, target)
    assert result.comparator == "json:category,priority"
    assert result.passed is True
    assert result.score == 1.0
    assert "all 2 scoped fields match" in result.detail
    # The out-of-scope difference is still visible, marked informational.
    assert "out of scope (informational)" in result.detail
    assert "summary" in result.detail


async def test_json_scoped_mismatch_scores_over_scoped_fields_only():
    baseline = _resp('{"category": "billing", "priority": "high", "summary": "x"}')
    target = _resp('{"category": "billing", "priority": "medium", "summary": "y"}')
    result = await JsonComparator(fields=["category", "priority"]).compare("p", baseline, target)
    assert result.passed is False
    assert result.score == pytest.approx(1 / 2)
    assert "priority: high→medium" in result.detail


async def test_json_scope_covers_nested_subtrees_and_list_indices():
    baseline = _resp('{"meta": {"source": "web", "spam": false}, "labels": ["a", "b"], "note": "x"}')
    target = _resp('{"meta": {"source": "api", "spam": false}, "labels": ["a", "c"], "note": "y"}')
    # "meta" covers meta.source and meta.spam; "labels[1]" is one list slot.
    result = await JsonComparator(fields=["meta", "labels[1]"]).compare("p", baseline, target)
    assert result.passed is False
    assert result.score == pytest.approx(1 / 3)  # spam matches; source and labels[1] differ
    assert "meta.source: web→api" in result.detail
    assert "labels[1]: b→c" in result.detail
    assert "note" not in result.detail.split("out of scope")[0]  # note never drives the verdict


async def test_json_scope_field_missing_in_target_fails_the_row():
    baseline = _resp('{"category": "bug", "priority": "low"}')
    target = _resp('{"category": "bug"}')
    result = await JsonComparator(fields=["category", "priority"]).compare("p", baseline, target)
    assert result.passed is False
    assert "missing in target: priority" in result.detail


async def test_json_scope_absent_from_both_payloads_is_noted_not_failed():
    baseline = _resp('{"category": "bug"}')
    target = _resp('{"category": "bug"}')
    result = await JsonComparator(fields=["category", "severity"]).compare("p", baseline, target)
    assert result.passed is True
    assert result.error is False
    assert "scoped fields absent from both payloads: severity" in result.detail


async def test_json_scope_matching_nothing_anywhere_is_a_comparator_error():
    # Most likely a typo in the spec — silent green would be worse.
    result = await JsonComparator(fields=["cattegory"]).compare(
        "p", _resp('{"category": "bug"}'), _resp('{"category": "bug"}')
    )
    assert result.error is True
    assert result.passed is None
    assert "cattegory" in result.detail


async def test_json_scope_does_not_prefix_match_sibling_field_names():
    # Scope "cat" must not cover "category": only ".", "[" or exact match extend.
    result = await JsonComparator(fields=["cat"]).compare(
        "p", _resp('{"category": "bug"}'), _resp('{"category": "feature"}')
    )
    assert result.error is True  # "cat" matched nothing


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


def _judge_handler(equivalent: bool, score: float, calls: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] = calls.get("n", 0) + 1
        verdict = json.dumps({"equivalent": equivalent, "score": score, "reason": "r"})
        return httpx.Response(
            200,
            json={
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": verdict}],
                "stop_reason": "end_turn",
            },
        )

    return handler


async def test_judge_flags_boolean_vs_score_inconsistency(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    async def verdict_of(equivalent: bool, score: float):
        transport = httpx.MockTransport(_judge_handler(equivalent, score, {}))
        async with httpx.AsyncClient(transport=transport) as http:
            return await JudgeComparator(http).compare("p", _resp("a"), _resp("b"))

    # equivalent=false at a high score: passed follows the boolean, flagged.
    result = await verdict_of(False, 0.85)
    assert result.passed is False and result.score == pytest.approx(0.85)
    assert "inconsistent verdict: equivalent=false" in result.detail

    # equivalent=true at a low score: also flagged.
    result = await verdict_of(True, 0.3)
    assert result.passed is True
    assert "inconsistent verdict: equivalent=true" in result.detail

    # Consistent verdicts are not flagged.
    result = await verdict_of(True, 0.85)
    assert result.passed is True and "inconsistent" not in result.detail
    result = await verdict_of(False, 0.3)
    assert result.passed is False and "inconsistent" not in result.detail


async def test_judge_verdict_is_cached_in_the_store(monkeypatch):
    from agentrec import InMemoryStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = InMemoryStore()
    calls: dict = {}

    async with httpx.AsyncClient(transport=httpx.MockTransport(_judge_handler(True, 0.9, calls))) as http:
        judge = JudgeComparator(http, store=store)
        first = await judge.compare("p", _resp("baseline text"), _resp("target text"))
        second = await judge.compare("p", _resp("baseline text"), _resp("target text"))
        other = await judge.compare("p", _resp("baseline text"), _resp("different target"))

    assert calls["n"] == 2  # one buy per distinct (baseline, target) pair
    assert first.passed is True and "[cached]" not in first.detail
    assert second.passed is second.passed is True
    assert second.score == pytest.approx(first.score)
    assert "[cached]" in second.detail
    assert "[cached]" not in other.detail

    cache_id = judge.cache_id("baseline text", "target text")
    assert cache_id.startswith("judge__")
    assert await store.has(cache_id)
    saved = await store.load(cache_id)
    assert saved.metadata["judge_model"] == "claude-opus-4-8"


async def test_judge_cached_verdict_survives_gzip_content_encoding(monkeypatch):
    """The cassette stores the DECODED body, so the gzip header must not be kept.

    Regression: the live path reads the decompressed payload, but the original
    response headers still said content-encoding: gzip — replaying that
    cassette tried to gunzip plain JSON and errored.
    """
    import gzip

    from agentrec import InMemoryStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = InMemoryStore()

    def handler(request: httpx.Request) -> httpx.Response:
        verdict = '{"equivalent": true, "score": 0.9, "reason": "same"}'
        body = json.dumps(
            {"model": "claude-opus-4-8", "content": [{"type": "text", "text": verdict}]}
        ).encode()
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip", "content-type": "application/json"},
            content=gzip.compress(body),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        live = await JudgeComparator(http, store=store).compare("p", _resp("a"), _resp("b"))
    assert live.passed is True

    # Replay offline: must decode cleanly, no socket.
    offline = JudgeComparator(None, store=store, offline=True)
    cached = await offline.compare("p", _resp("a"), _resp("b"))
    assert cached.passed is True
    assert cached.score == pytest.approx(0.9)
    assert "[cached]" in cached.detail


async def test_judge_offline_uses_cache_and_errors_without_it(monkeypatch):
    from agentrec import InMemoryStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = InMemoryStore()

    # Record one verdict online.
    async with httpx.AsyncClient(transport=httpx.MockTransport(_judge_handler(True, 0.9, {}))) as http:
        await JudgeComparator(http, store=store).compare("p", _resp("a"), _resp("b"))

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("offline judge must not touch the network")

    async with httpx.AsyncClient(transport=httpx.MockTransport(explode)) as http:
        offline_judge = JudgeComparator(http, store=store, offline=True)
        cached = await offline_judge.compare("p", _resp("a"), _resp("b"))
        missing = await offline_judge.compare("p", _resp("a"), _resp("never judged"))

    assert cached.passed is True and "[cached]" in cached.detail
    assert missing.error is True and missing.passed is None
    assert "no cached verdict" in missing.detail


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
# Two-judge (second-opinion) mode
# ---------------------------------------------------------------------------


def _per_model_judge_handler(verdicts: dict, calls: dict):
    """Mock judge that answers per request model, counting calls per model."""

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        calls[model] = calls.get(model, 0) + 1
        equivalent, score = verdicts[model]
        verdict = json.dumps(
            {"equivalent": equivalent, "score": score, "reason": f"{model} reason"}
        )
        return httpx.Response(
            200,
            json={
                "model": model,
                "content": [{"type": "text", "text": verdict}],
                "stop_reason": "end_turn",
            },
        )

    return handler


async def test_two_judges_agree_pass_and_average(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls: dict = {}
    handler = _per_model_judge_handler(
        {"claude-opus-4-8": (True, 0.9), "claude-haiku-4-5": (True, 0.8)}, calls
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        judge = JudgeComparator(
            http, judge_model="claude-opus-4-8", second_judge_model="claude-haiku-4-5"
        )
        result = await judge.compare("p", _resp("a"), _resp("b"))

    assert result.passed is True
    assert result.score == pytest.approx((0.9 + 0.8) / 2)
    assert "claude-opus-4-8: equivalent" in result.detail
    assert "claude-haiku-4-5: equivalent" in result.detail
    assert "disagreed" not in result.detail
    assert calls == {"claude-opus-4-8": 1, "claude-haiku-4-5": 1}


async def test_two_judges_disagreement_fails_and_is_flagged(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls: dict = {}
    handler = _per_model_judge_handler(
        {"claude-opus-4-8": (True, 0.9), "claude-haiku-4-5": (False, 0.2)}, calls
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        judge = JudgeComparator(
            http, judge_model="claude-opus-4-8", second_judge_model="claude-haiku-4-5"
        )
        result = await judge.compare("p", _resp("a"), _resp("b"))

    # Gate-safe: a split decision does not pass, and the split is flagged.
    assert result.passed is False
    assert "[judges disagreed]" in result.detail
    assert result.score == pytest.approx((0.9 + 0.2) / 2)


async def test_two_judges_cache_independently(monkeypatch):
    from agentrec import InMemoryStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = InMemoryStore()
    calls: dict = {}
    handler = _per_model_judge_handler(
        {"claude-opus-4-8": (True, 0.9), "claude-haiku-4-5": (True, 0.7)}, calls
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        judge = JudgeComparator(
            http,
            judge_model="claude-opus-4-8",
            second_judge_model="claude-haiku-4-5",
            store=store,
        )
        first = await judge.compare("p", _resp("a"), _resp("b"))
        second = await judge.compare("p", _resp("a"), _resp("b"))

    # One buy per model on the first call; the second call is fully cached.
    assert calls == {"claude-opus-4-8": 1, "claude-haiku-4-5": 1}
    assert first.passed is True and second.passed is True
    assert "[cached]" in second.detail
    # Each model cached its verdict under its own id (texts are "a"/"b").
    opus_id = judge.cache_id("a", "b", model="claude-opus-4-8")
    haiku_id = judge.cache_id("a", "b", model="claude-haiku-4-5")
    assert opus_id != haiku_id
    assert await store.has(opus_id) and await store.has(haiku_id)
    assert opus_id.startswith("judge__") and haiku_id.startswith("judge__")


async def test_blank_second_judge_is_ignored(monkeypatch):
    """An empty AGENTREC_JUDGE_MODEL_2 must not silently double the judge bill."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls: dict = {}
    handler = _per_model_judge_handler({"claude-opus-4-8": (True, 0.9)}, calls)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        judge = JudgeComparator(http, judge_model="claude-opus-4-8", second_judge_model="")
        result = await judge.compare("p", _resp("a"), _resp("b"))
    assert result.passed is True
    assert result.detail == "claude-opus-4-8 reason"  # single-judge detail shape
    assert calls == {"claude-opus-4-8": 1}


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def test_build_comparators_spec():
    names = [c.name for c in build_comparators("exact, judge")]
    assert names == ["exact", "judge"]

    names = [c.name for c in build_comparators("json")]
    assert names == ["json"]

    names = [c.name for c in build_comparators("all")]
    assert names == ["exact", "fuzzy", "json", "toolcalls", "embedding", "judge"]

    with pytest.raises(ValueError, match="unknown comparator"):
        build_comparators("exact,levenshtein")
    with pytest.raises(ValueError, match="no comparators"):
        build_comparators(" , ")


def test_build_comparators_scoped_json_spec():
    # Tokens after json:… that are not comparator names continue its scope.
    names = [c.name for c in build_comparators("exact,fuzzy,json:category,priority")]
    assert names == ["exact", "fuzzy", "json:category,priority"]

    # A comparator name token closes the open scope.
    names = [c.name for c in build_comparators("json:category,fuzzy")]
    assert names == ["json:category", "fuzzy"]

    # Scoped and unscoped json may coexist; duplicates collapse.
    names = [c.name for c in build_comparators("json,json:category,priority,json")]
    assert names == ["json", "json:category,priority"]

    with pytest.raises(ValueError, match="does not take a field scope"):
        build_comparators("fuzzy:0.7")
    with pytest.raises(ValueError, match="needs at least one field"):
        build_comparators("json:")
    with pytest.raises(ValueError, match="unknown comparator"):
        build_comparators("category,json")  # bare field with no open scope
