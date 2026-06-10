"""
Comparators score a baseline response against a target-model response.

The migration runner evaluates *all* selected comparators per prompt in one
pass, so a single ``migrate`` run can report exact-match, fuzzy similarity,
embedding similarity and judge verdicts side by side.

* ``exact``     — normalized string equality.  The right metric for
                  classification-style outputs ("positive" vs "Positive ").
* ``fuzzy``     — ``difflib.SequenceMatcher`` ratio; offline, dependency-free.
* ``embedding`` — cosine similarity of OpenAI embeddings (live API call).
* ``judge``     — an LLM scores semantic equivalence (live API call).

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

OFFLINE_COMPARATOR_NAMES = ("exact", "fuzzy")
ALL_COMPARATOR_NAMES = ("exact", "fuzzy", "embedding", "judge")

_WHITESPACE = re.compile(r"\s+")


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
        matched = _normalize(baseline.text) == _normalize(target.text)
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
            None, _normalize(baseline.text), _normalize(target.text)
        ).ratio()
        return ComparisonResult(
            comparator=self.name,
            score=score,
            passed=score >= self._threshold,
            detail=f"sequence similarity {score:.2f} (threshold {self._threshold})",
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


def _first_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for start in range(len(text)):
        if text[start] != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
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
        verdict = _first_json_object(decoded.text)

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
        "embedding": lambda: EmbeddingComparator(
            http, model=embedding_model, threshold=embedding_threshold
        ),
        "judge": lambda: JudgeComparator(http, judge_model=judge_model),
    }
    return [factories[name]() for name in seen]
