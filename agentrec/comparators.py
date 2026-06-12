"""
Comparators score a baseline response against a target-model response.

The migration runner evaluates *all* selected comparators per prompt in one
pass, so a single ``migrate`` run can report exact-match, fuzzy similarity,
embedding similarity and judge verdicts side by side.

* ``exact``     — normalized string equality.  The right metric for
                  classification-style outputs ("positive" vs "Positive ").
* ``fuzzy``     — ``difflib.SequenceMatcher`` ratio; offline, dependency-free.
* ``json``      — structural JSON comparison: parses both sides and scores the
                  fraction of matching scalar fields, so a category/priority
                  match with a differing free-text field scores high, not zero.
* ``embedding`` — cosine similarity of OpenAI embeddings (live API call).
* ``judge``     — an LLM scores semantic equivalence (live API call).

The offline comparators tolerate a markdown code fence wrapping the whole
payload (``` ```json … ``` ```): some target models fence structured output
even when told not to, and the fence is presentation, not content.

A comparator failure (missing API key, malformed judge reply) degrades to an
errored :class:`ComparisonResult` on that row — it never crashes the run.
"""
from __future__ import annotations

import difflib
import json
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import httpx

from .providers import Conversation, DecodedResponse, adapter_for_model, adapter_for_provider

OFFLINE_COMPARATOR_NAMES = ("exact", "fuzzy", "json")
ALL_COMPARATOR_NAMES = ("exact", "fuzzy", "json", "embedding", "judge")

_WHITESPACE = re.compile(r"\s+")

# A single markdown code fence (```lang ... ```) wrapping the ENTIRE payload.
# Anchored at both ends on purpose: inner backticks and partial fences are
# content, not wrapping, and must survive untouched.
_FENCE = re.compile(r"^\s*```[\w+-]*[ \t]*\r?\n(.*?)\r?\n?[ \t]*```\s*$", re.DOTALL)


def _strip_fence(text: str) -> str:
    """Payload without a whole-string markdown code fence, if one wraps it.

    Models (Anthropic's especially) often fence structured output in
    ```json … ``` even when asked not to; the fence is presentation, not
    content, so the offline comparators ignore it rather than zeroing every
    fenced-vs-bare pair.
    """
    match = _FENCE.match(text)
    return match.group(1) if match else text


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().casefold()


def _clip(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + " …[truncated]"


@dataclass(frozen=True)
class ComparisonResult:
    comparator: str
    score: float  # 0.0–1.0
    passed: Optional[bool]  # None when pass/fail is not meaningful
    detail: str = ""
    error: bool = False  # True when the comparator itself failed


class Comparator(ABC):
    """Scores how well *target* preserves the behaviour of *baseline*."""

    name: str

    @abstractmethod
    async def compare(
        self, prompt: str, baseline: DecodedResponse, target: DecodedResponse
    ) -> ComparisonResult:
        ...


class ExactMatchComparator(Comparator):
    name = "exact"

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        matched = _normalize(_strip_fence(baseline.text)) == _normalize(_strip_fence(target.text))
        return ComparisonResult(
            comparator=self.name,
            score=1.0 if matched else 0.0,
            passed=matched,
            detail="normalized texts match" if matched else "normalized texts differ",
        )


class FuzzyComparator(Comparator):
    name = "fuzzy"

    def __init__(self, threshold: float = 0.8) -> None:
        self._threshold = threshold

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        score = difflib.SequenceMatcher(
            None, _normalize(_strip_fence(baseline.text)), _normalize(_strip_fence(target.text))
        ).ratio()
        return ComparisonResult(
            comparator=self.name,
            score=score,
            passed=score >= self._threshold,
            detail=f"sequence similarity {score:.2f} (threshold {self._threshold})",
        )


# Sentinels for empty containers: an empty object/array is a real value at its
# path (so {"a": {}} matches {"a": {}} and mismatches {"a": {"b": 1}}), but it
# must never compare equal to the literal strings "{}" / "[]".
_EMPTY_OBJECT = ("<empty object>",)
_EMPTY_ARRAY = ("<empty array>",)


def _flatten_json(value, path: str, out: Dict[str, object]) -> None:
    """Flatten *value* into ``out`` as scalar leaves keyed by dotted path.

    Dicts recurse by key (``a.b``), lists by index (``a[0]``); a top-level
    scalar lands at ``$``.
    """
    if isinstance(value, dict):
        if not value:
            out[path or "$"] = _EMPTY_OBJECT
        for key, item in value.items():
            _flatten_json(item, f"{path}.{key}" if path else str(key), out)
    elif isinstance(value, list):
        if not value:
            out[path or "$"] = _EMPTY_ARRAY
        for index, item in enumerate(value):
            _flatten_json(item, f"{path or '$'}[{index}]", out)
    else:
        out[path or "$"] = value


def _scalars_match(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b  # bool subclasses int: True must not match 1
    if isinstance(a, str) and isinstance(b, str):
        return _normalize(a) == _normalize(b)
    return a == b  # numbers (1 == 1.0), None, empty-container sentinels


def _fmt_scalar(value) -> str:
    if value is _EMPTY_OBJECT:
        return "{}"
    if value is _EMPTY_ARRAY:
        return "[]"
    if isinstance(value, str):
        return value
    return json.dumps(value)


class JsonComparator(Comparator):
    """Field-by-field comparison of JSON payloads.

    Both sides are parsed (after fence stripping) and flattened to scalar
    fields; the score is the fraction of fields that match, so structured
    outputs where the fixed fields agree but a free-text field differs score
    high instead of zero.  ``passed`` requires every scalar field to match.
    An unparseable baseline is a comparator error; an unparseable target is a
    failed comparison — the target genuinely broke the contract.
    """

    name = "json"

    _MAX_DIFFS = 6

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        try:
            baseline_value = json.loads(_strip_fence(baseline.text))
        except ValueError as exc:
            return ComparisonResult(
                comparator=self.name,
                score=0.0,
                passed=None,
                detail=f"baseline is not valid JSON: {exc}",
                error=True,
            )
        try:
            target_value = json.loads(_strip_fence(target.text))
        except ValueError as exc:
            return ComparisonResult(
                comparator=self.name,
                score=0.0,
                passed=False,
                detail=f"target is not valid JSON: {exc}",
            )

        baseline_fields: Dict[str, object] = {}
        target_fields: Dict[str, object] = {}
        _flatten_json(baseline_value, "", baseline_fields)
        _flatten_json(target_value, "", target_fields)

        diffs: List[str] = []
        matched = 0
        all_paths = list(baseline_fields) + [
            path for path in target_fields if path not in baseline_fields
        ]
        for path in all_paths:
            if path not in target_fields:
                diffs.append(f"missing in target: {path}")
            elif path not in baseline_fields:
                diffs.append(f"extra in target: {path}")
            elif _scalars_match(baseline_fields[path], target_fields[path]):
                matched += 1
            else:
                diffs.append(
                    f"{path}: {_fmt_scalar(baseline_fields[path])}"
                    f"→{_fmt_scalar(target_fields[path])}"
                )

        total = len(all_paths)
        score = matched / total if total else 1.0
        passed = matched == total
        if passed:
            detail = f"all {total} fields match" if total else "both payloads are empty JSON"
        else:
            shown = diffs[: self._MAX_DIFFS]
            if len(diffs) > self._MAX_DIFFS:
                shown.append(f"… (+{len(diffs) - self._MAX_DIFFS} more)")
            detail = "; ".join(shown)
        return ComparisonResult(
            comparator=self.name, score=score, passed=passed, detail=detail
        )


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0:
        return 0.0
    return dot / norm


class _HttpComparator(Comparator):
    """Shared plumbing for comparators that call an API via httpx."""

    def __init__(self, http: Optional[httpx.AsyncClient] = None) -> None:
        self._http = http

    async def _post(self, url: str, headers: Dict[str, str], body: dict) -> httpx.Response:
        if self._http is not None:
            return await self._http.post(url, headers=headers, json=body)
        async with httpx.AsyncClient(timeout=60.0) as client:
            return await client.post(url, headers=headers, json=body)


class EmbeddingComparator(_HttpComparator):
    name = "embedding"

    embeddings_url = "https://api.openai.com/v1/embeddings"

    def __init__(
        self,
        http: Optional[httpx.AsyncClient] = None,
        *,
        model: str = "text-embedding-3-small",
        threshold: float = 0.8,
    ) -> None:
        super().__init__(http)
        self._model = model
        self._threshold = threshold

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        headers = {
            "Authorization": f"Bearer {adapter_for_provider('openai').api_key()}",
            "Content-Type": "application/json",
        }
        body = {"model": self._model, "input": [_clip(baseline.text), _clip(target.text)]}
        response = await self._post(self.embeddings_url, headers, body)
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        score = max(0.0, min(1.0, cosine_similarity(data[0]["embedding"], data[1]["embedding"])))
        return ComparisonResult(
            comparator=self.name,
            score=score,
            passed=score >= self._threshold,
            detail=f"cosine similarity {score:.2f} via {self._model} (threshold {self._threshold})",
        )


_JUDGE_SYSTEM = (
    "You compare two AI assistant responses to the same prompt and judge whether "
    "the candidate response is an acceptable substitute for the baseline response. "
    "Judge semantic equivalence of the substantive content, not style or length. "
    'Reply with ONLY a JSON object: {"equivalent": true|false, "score": 0.0-1.0, '
    '"reason": "<one sentence>"}'
)

_JUDGE_TEMPLATE = """<prompt>
{prompt}
</prompt>

<baseline_response>
{baseline}
</baseline_response>

<candidate_response>
{target}
</candidate_response>"""


def _judge_verdict(text: str) -> dict:
    """Extract the verdict object from a judge reply.

    Prefers the first JSON object that actually looks like a verdict (has an
    ``equivalent`` key), so prose or an example object emitted before the
    verdict is never scored by mistake; falls back to the first JSON object
    found when no verdict-shaped one exists.
    """
    decoder = json.JSONDecoder()
    fallback: Optional[dict] = None
    for start in range(len(text)):
        if text[start] != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(obj, dict):
            if "equivalent" in obj:
                return obj
            if fallback is None:
                fallback = obj
    if fallback is not None:
        return fallback
    raise ValueError(f"no JSON object found in judge reply: {text[:200]!r}")


class JudgeComparator(_HttpComparator):
    name = "judge"

    def __init__(
        self,
        http: Optional[httpx.AsyncClient] = None,
        *,
        judge_model: str = "claude-opus-4-8",
    ) -> None:
        super().__init__(http)
        self._judge_model = judge_model

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        adapter = adapter_for_model(self._judge_model)
        conversation = Conversation(
            system=_JUDGE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": _JUDGE_TEMPLATE.format(
                        prompt=_clip(prompt),
                        baseline=_clip(baseline.text),
                        target=_clip(target.text),
                    ),
                }
            ],
            # No sampling params: the newest judge models reject them.
            max_tokens=1024,
        )
        url, headers, body = adapter.build_request(conversation, self._judge_model)
        response = await self._post(url, headers, body)
        response.raise_for_status()
        decoded = adapter.decode_response(await response.aread(), is_sse=False)
        verdict = _judge_verdict(decoded.text)

        equivalent = bool(verdict.get("equivalent"))
        raw_score = verdict.get("score")
        score = float(raw_score) if isinstance(raw_score, (int, float)) else (1.0 if equivalent else 0.0)
        score = max(0.0, min(1.0, score))
        return ComparisonResult(
            comparator=self.name,
            score=score,
            passed=equivalent,
            detail=str(verdict.get("reason", "")) or f"judge {self._judge_model} verdict",
        )


def build_comparators(
    spec: str,
    *,
    judge_model: str = "claude-opus-4-8",
    embedding_model: str = "text-embedding-3-small",
    fuzzy_threshold: float = 0.8,
    embedding_threshold: float = 0.8,
    http: Optional[httpx.AsyncClient] = None,
) -> List[Comparator]:
    """Parse a ``--compare`` spec like ``"exact,judge"`` or ``"all"``."""
    names = (
        list(ALL_COMPARATOR_NAMES)
        if spec.strip().lower() == "all"
        else [name.strip().lower() for name in spec.split(",") if name.strip()]
    )
    seen: List[str] = []
    for name in names:
        if name not in ALL_COMPARATOR_NAMES:
            raise ValueError(
                f"unknown comparator {name!r}; expected any of "
                f"{', '.join(ALL_COMPARATOR_NAMES)} or 'all'"
            )
        if name not in seen:
            seen.append(name)
    if not seen:
        raise ValueError("no comparators selected")

    factories = {
        "exact": lambda: ExactMatchComparator(),
        "fuzzy": lambda: FuzzyComparator(threshold=fuzzy_threshold),
        "json": lambda: JsonComparator(),
        "embedding": lambda: EmbeddingComparator(
            http, model=embedding_model, threshold=embedding_threshold
        ),
        "judge": lambda: JudgeComparator(http, judge_model=judge_model),
    }
    return [factories[name]() for name in seen]
