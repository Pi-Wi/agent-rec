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
                  A field scope (``json:category,priority``) restricts which
                  fields drive the verdict; the rest become informational.
* ``toolcalls`` — which tools the response called and with what arguments
                  (selection + arguments only; recorded tools are never
                  executed).  Offline, dependency-free.
* ``embedding`` — cosine similarity of OpenAI embeddings (live API call).
* ``judge``     — an LLM scores semantic equivalence (live API call; verdicts
                  are cached into the corpus when a store is supplied, so a
                  re-run on unchanged texts costs nothing).  Configurable model,
                  and optionally a *second* judge for a second opinion — two
                  judges run, each verdict cached on its own model, and a
                  disagreement is flagged and fails (the gate-safe choice).

The offline comparators tolerate a markdown code fence wrapping the whole
payload (``` ```json … ``` ```): some target models fence structured output
even when told not to, and the fence is presentation, not content.

A comparator failure (missing API key, malformed judge reply) degrades to an
errored :class:`ComparisonResult` on that row — it never crashes the run.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import json
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest
from .keying import _digest, _sanitize, fingerprint
from .providers import (
    Conversation,
    DecodedResponse,
    adapter_for_model,
    adapter_for_provider,
    decode_interaction,
    render_response,
)
from .store import InteractionStore

OFFLINE_COMPARATOR_NAMES = ("exact", "fuzzy", "json", "toolcalls")
ALL_COMPARATOR_NAMES = ("exact", "fuzzy", "json", "toolcalls", "embedding", "judge")

# Corpus-id prefix for cached judge verdicts; the migration runner excludes
# these from the baseline set, like ``migration__`` cassettes.
JUDGE_PREFIX = "judge__"

# Judge model used when neither --judge-model nor AGENTREC_JUDGE_MODEL[_1] is set.
DEFAULT_JUDGE_MODEL = "claude-opus-4-8"


class _OfflineMiss(Exception):
    """Internal: an offline judge has no cached verdict for *model* on this row."""

    def __init__(self, model: str) -> None:
        super().__init__(model)
        self.model = model

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


def _comparable_text(decoded: DecodedResponse) -> str:
    """The text a string comparator should look at.

    ``render_response`` appends canonical tool-call lines, so a tool-calling
    response compares on what the model decided to do instead of on an empty
    string (where every pair would trivially "match").  For text-only
    responses this is exactly ``decoded.text``.
    """
    return render_response(decoded)


class ExactMatchComparator(Comparator):
    name = "exact"

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        matched = _normalize(_strip_fence(_comparable_text(baseline))) == _normalize(
            _strip_fence(_comparable_text(target))
        )
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
            None,
            _normalize(_strip_fence(_comparable_text(baseline))),
            _normalize(_strip_fence(_comparable_text(target))),
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


# Diffs shown in a comparator's detail are capped so one wildly-divergent row
# can't produce a kilobyte of text; the JSON and tool-call comparators share
# both the cap and the field-by-field walk below.
_MAX_DIFFS = 6


def _cap_diffs(diffs: List[str], limit: int = _MAX_DIFFS) -> List[str]:
    """First *limit* diffs, with a ``… (+N more)`` tail when truncated."""
    shown = diffs[:limit]
    if len(diffs) > limit:
        shown.append(f"… (+{len(diffs) - limit} more)")
    return shown


def _union_paths(baseline_fields: Dict[str, object], target_fields: Dict[str, object]) -> List[str]:
    """Every leaf path across both maps: baseline order first, then target-only."""
    return list(baseline_fields) + [path for path in target_fields if path not in baseline_fields]


def _classify_path(
    path: str, baseline_fields: Dict[str, object], target_fields: Dict[str, object]
) -> Tuple[str, Optional[str]]:
    """Classify one leaf path as ``match`` / ``missing`` / ``extra`` / ``mismatch``.

    Returns ``(kind, change)`` where *change* is the ``baseline→target``
    rendering for a value mismatch (``None`` otherwise); each caller supplies
    its own wording for the missing/extra/mismatch cases.
    """
    if path not in target_fields:
        return "missing", None
    if path not in baseline_fields:
        return "extra", None
    if _scalars_match(baseline_fields[path], target_fields[path]):
        return "match", None
    return "mismatch", f"{_fmt_scalar(baseline_fields[path])}→{_fmt_scalar(target_fields[path])}"


class JsonComparator(Comparator):
    """Field-by-field comparison of JSON payloads.

    Both sides are parsed (after fence stripping) and flattened to scalar
    fields; the score is the fraction of fields that match, so structured
    outputs where the fixed fields agree but a free-text field differs score
    high instead of zero.  ``passed`` requires every scalar field to match.
    An unparseable baseline is a comparator error; an unparseable target is a
    failed comparison — the target genuinely broke the contract.

    A field scope (``fields=["category", "priority"]``, spelled
    ``json:category,priority`` in a ``--compare`` spec) restricts which fields
    drive the score and the pass/fail verdict — the fit for payloads that mix
    fixed fields with free text (scope the fixed fields; the free text stops
    diluting the mean).  Scope entries use the flattened-path syntax: dotted
    for nested objects (``meta.source``), ``[i]`` for list indices
    (``labels[0]``); a scope entry covers its whole subtree.  Out-of-scope
    differences are still reported in ``detail``, marked informational.  A
    scope that matches nothing in either payload is a comparator error (most
    likely a typo — silent green would be worse).
    """

    name = "json"

    def __init__(self, fields: Optional[Sequence[str]] = None) -> None:
        self._fields: Tuple[str, ...] = tuple(fields) if fields else ()
        if self._fields:
            self.name = f"json:{','.join(self._fields)}"

    def _in_scope(self, path: str) -> bool:
        return any(
            path == field or path.startswith(field + ".") or path.startswith(field + "[")
            for field in self._fields
        )

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        # Compare the response's prose (``.text``), not ``_comparable_text`` (which
        # appends tool-call lines): a JSON-mode/structured response is the JSON
        # body, and a tool-calling step is the ``toolcalls`` comparator's job —
        # appending non-JSON tool-call lines here would only break json.loads.
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

        diffs: List[str] = []  # in-scope mismatches: these drive the verdict
        info_diffs: List[str] = []  # out-of-scope mismatches: reported, not scored
        matched = 0
        total = 0
        all_paths = _union_paths(baseline_fields, target_fields)
        for path in all_paths:
            kind, change = _classify_path(path, baseline_fields, target_fields)
            if kind == "missing":
                diff = f"missing in target: {path}"
            elif kind == "extra":
                diff = f"extra in target: {path}"
            elif kind == "match":
                diff = None
            else:
                diff = f"{path}: {change}"
            if not self._fields or self._in_scope(path):
                total += 1
                if diff is None:
                    matched += 1
                else:
                    diffs.append(diff)
            elif diff is not None:
                info_diffs.append(diff)

        unmatched_scopes = [
            field
            for field in self._fields
            if not any(
                path == field or path.startswith(field + ".") or path.startswith(field + "[")
                for path in all_paths
            )
        ]
        if self._fields and len(unmatched_scopes) == len(self._fields):
            return ComparisonResult(
                comparator=self.name,
                score=0.0,
                passed=None,
                detail=(
                    f"none of the scoped fields ({', '.join(self._fields)}) exist in "
                    "either payload — check the field paths in the comparator spec"
                ),
                error=True,
            )

        score = matched / total if total else 1.0
        passed = matched == total
        scoped = " scoped" if self._fields else ""
        if passed:
            detail = f"all {total}{scoped} fields match" if total else "both payloads are empty JSON"
        else:
            detail = "; ".join(_cap_diffs(diffs))
        if unmatched_scopes:
            detail += f" · scoped fields absent from both payloads: {', '.join(unmatched_scopes)}"
        if info_diffs:
            detail += " · out of scope (informational): " + "; ".join(_cap_diffs(info_diffs))
        return ComparisonResult(
            comparator=self.name, score=score, passed=passed, detail=detail
        )


class ToolCallsComparator(Comparator):
    """Compare which tools were called and with what arguments — never executes them.

    Calls are paired by position (an agent step's tool order is part of its
    behaviour).  Each pair scores 0 when the tool *names* differ, otherwise
    the fraction of matching argument fields (same flattening rules as the
    ``json`` comparator); a missing or extra call scores 0.  The row score is
    the mean over ``max(len(baseline), len(target))`` pairs, and ``passed``
    requires every pair to match exactly.  Two responses that both called no
    tools pass trivially — for tool-capable corpora "didn't call a tool" is
    itself behaviour worth confirming.
    """

    name = "toolcalls"

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        baseline_calls = list(baseline.tool_calls)
        target_calls = list(target.tool_calls)
        if not baseline_calls and not target_calls:
            return ComparisonResult(
                comparator=self.name,
                score=1.0,
                passed=True,
                detail="neither response called tools",
            )

        diffs: List[str] = []
        scores: List[float] = []
        for index in range(max(len(baseline_calls), len(target_calls))):
            if index >= len(baseline_calls):
                call = target_calls[index]
                scores.append(0.0)
                diffs.append(f"call[{index}] extra in target: {call.name}")
                continue
            if index >= len(target_calls):
                call = baseline_calls[index]
                scores.append(0.0)
                diffs.append(f"call[{index}] missing in target: {call.name}")
                continue
            b_call, t_call = baseline_calls[index], target_calls[index]
            if b_call.name != t_call.name:
                scores.append(0.0)
                diffs.append(f"call[{index}]: {b_call.name}→{t_call.name}")
                continue
            b_fields: Dict[str, object] = {}
            t_fields: Dict[str, object] = {}
            _flatten_json(b_call.arguments, "", b_fields)
            _flatten_json(t_call.arguments, "", t_fields)
            matched = 0
            total = 0
            for path in _union_paths(b_fields, t_fields):
                total += 1
                kind, change = _classify_path(path, b_fields, t_fields)
                if kind == "match":
                    matched += 1
                elif kind == "missing":
                    diffs.append(f"call[{index}] {b_call.name}: missing in target: {path}")
                elif kind == "extra":
                    diffs.append(f"call[{index}] {b_call.name}: extra in target: {path}")
                else:
                    diffs.append(f"call[{index}] {b_call.name}.{path}: {change}")
            scores.append(matched / total if total else 1.0)

        score = sum(scores) / len(scores)
        passed = not diffs
        if passed:
            names = ", ".join(call.name for call in baseline_calls)
            detail = f"tool calls match ({names})"
        else:
            detail = "; ".join(_cap_diffs(diffs))
        return ComparisonResult(comparator=self.name, score=score, passed=passed, detail=detail)


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
        body = {
            "model": self._model,
            "input": [_clip(_comparable_text(baseline)), _clip(_comparable_text(target))],
        }
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
    """LLM-as-judge equivalence verdicts, with corpus-cached results.

    The judge model is configurable (``judge_model``).  Supply a
    ``second_judge_model`` for a **second opinion**: both judges run, and the
    row's verdict combines theirs — ``passed`` is True only when *both* call
    the responses equivalent, so a disagreement (or a unanimous "not
    equivalent") fails, the gate-safe choice for a second-opinion run.  A
    disagreement is flagged ``[judges disagreed]`` in ``detail`` so a human
    sees it while the gate still reads the boolean.

    When a *store* is supplied, each verdict is persisted as a corpus cassette
    keyed on ``(judge_model, baseline_text, target_text)`` — the same
    full-interaction shape as a ``migration__`` cassette — so re-rendering a
    report on unchanged texts replays the verdict instead of re-buying it.
    Two judges cache independently (each on its own model), so existing
    single-judge caches stay valid.  With ``offline=True`` no socket is ever
    opened: rows without a cached verdict degrade to errored comparisons.

    With a single judge, ``passed`` follows the judge's ``equivalent`` boolean.
    When the verdict's numeric score disagrees with the boolean (score ≥ 0.8
    but ``equivalent=false``, or score < 0.5 but ``equivalent=true``), the
    inconsistency is flagged in ``detail`` so report readers see it.
    """

    name = "judge"

    # Boolean-vs-score disagreement bands flagged in the detail text.
    _INCONSISTENT_HIGH = 0.8
    _INCONSISTENT_LOW = 0.5

    def __init__(
        self,
        http: Optional[httpx.AsyncClient] = None,
        *,
        judge_model: str = DEFAULT_JUDGE_MODEL,
        second_judge_model: Optional[str] = None,
        store: Optional[InteractionStore] = None,
        offline: bool = False,
    ) -> None:
        super().__init__(http)
        # One or two models, primary first.  A blank/duplicate second is ignored
        # so a stray empty env var doesn't accidentally double the judge bill.
        models = [judge_model]
        if second_judge_model and second_judge_model != judge_model:
            models.append(second_judge_model)
        self._judge_models: Tuple[str, ...] = tuple(models)
        self._store = store
        self._offline = offline

    def cache_id(self, baseline_text: str, target_text: str, *, model: Optional[str] = None) -> str:
        """Deterministic corpus id for one (judge_model, baseline, target) verdict.

        Keyed on the compared texts, not the prompt: the prompt only frames
        the comparison, and unchanged texts should reuse the verdict.  *model*
        defaults to the primary judge, so a single-judge cache id is byte-for-
        byte what earlier versions produced.
        """
        model = model or self._judge_models[0]
        digest = _digest(model, baseline_text, target_text)[:32]
        return f"{JUDGE_PREFIX}{_sanitize(model)}__{digest}"

    @staticmethod
    def _score_of(verdict: dict) -> Tuple[float, bool]:
        """``(clamped_score, explicit?)`` — explicit when the reply gave a number."""
        raw_score = verdict.get("score")
        explicit = isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool)
        equivalent = bool(verdict.get("equivalent"))
        score = float(raw_score) if explicit else (1.0 if equivalent else 0.0)
        return max(0.0, min(1.0, score)), explicit

    def _result(self, verdict: dict, *, model: str, cached: bool) -> ComparisonResult:
        equivalent = bool(verdict.get("equivalent"))
        score, explicit = self._score_of(verdict)
        detail = str(verdict.get("reason", "")) or f"judge {model} verdict"
        if explicit and not equivalent and score >= self._INCONSISTENT_HIGH:
            detail += (
                f" [inconsistent verdict: equivalent=false but score {score:.2f} >= "
                f"{self._INCONSISTENT_HIGH}; passed follows the boolean]"
            )
        elif explicit and equivalent and score < self._INCONSISTENT_LOW:
            detail += (
                f" [inconsistent verdict: equivalent=true but score {score:.2f} < "
                f"{self._INCONSISTENT_LOW}; passed follows the boolean]"
            )
        if cached:
            detail += " [cached]"
        return ComparisonResult(
            comparator=self.name, score=score, passed=equivalent, detail=detail
        )

    def _combined_result(
        self, per_judge: List[Tuple[str, dict, bool]]
    ) -> ComparisonResult:
        """Combine two+ judges' verdicts, flagging disagreement.

        ``passed`` is True only when every judge calls the responses
        equivalent; the score is the mean of theirs.  Each judge's verdict
        (and its ``[cached]`` state) is listed in ``detail``, prefixed with
        ``[judges disagreed]`` when they split.
        """
        equivalents = [bool(verdict.get("equivalent")) for _, verdict, _ in per_judge]
        scores = [self._score_of(verdict)[0] for _, verdict, _ in per_judge]
        passed = all(equivalents)
        disagreed = any(equivalents) and not all(equivalents)
        parts = []
        for (model, verdict, cached), equivalent, score in zip(per_judge, equivalents, scores):
            reason = str(verdict.get("reason", "")).strip()
            piece = f"{model}: {'equivalent' if equivalent else 'not equivalent'} ({score:.2f})"
            if reason:
                piece += f" — {reason}"
            if cached:
                piece += " [cached]"
            parts.append(piece)
        detail = "; ".join(parts)
        if disagreed:
            detail = "[judges disagreed] " + detail
        return ComparisonResult(
            comparator=self.name,
            score=sum(scores) / len(scores),
            passed=passed,
            detail=detail,
        )

    async def _save_verdict(
        self, model: str, cache_id: str, url: str, headers: Dict[str, str], body: dict,
        response: httpx.Response, payload: bytes,
    ) -> None:
        """Persist the judge call as a corpus cassette (best-effort).

        A cache-write failure must not void a verdict that was already bought;
        the next run simply re-asks.
        """
        request = httpx.Request("POST", url, headers=headers, json=body)
        request.read()
        # *payload* is the DECODED body (aread() decompresses), so the stored
        # headers must not claim a content-encoding/-length the chunk no
        # longer has — unlike the transports, which record raw network bytes.
        response_headers = [
            (name, value)
            for name, value in response.headers.raw
            if name.lower() not in (b"content-encoding", b"content-length")
        ]
        interaction = CapturedInteraction(
            request=CapturedRequest(
                method="POST",
                url=url,
                headers=list(request.headers.raw),
                content=request.content,
            ),
            response_status=response.status_code,
            response_headers=response_headers,
            response_extensions={},
            chunks=[CapturedChunk(data=payload)],
            metadata=fingerprint(request).as_metadata(),
        )
        interaction.metadata.update(
            {
                "judge_model": model,
                "judge_key": cache_id,
                "recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
        )
        try:
            await self._store.save(cache_id, interaction)
        except Exception:
            pass

    async def _verdict_for(
        self, model: str, prompt: str, baseline_text: str, target_text: str
    ) -> Tuple[dict, bool]:
        """``(verdict, cached?)`` from one judge *model*.

        Replays a cached verdict when present, else (online) buys and caches
        one.  Raises :class:`_OfflineMiss` when offline with no cached verdict,
        and lets a malformed-reply ``ValueError`` propagate (never cached) so
        the runner degrades the whole comparison to an errored result.
        """
        cache_id = self.cache_id(baseline_text, target_text, model=model) if self._store else None
        if cache_id and await self._store.has(cache_id):
            try:
                cached = decode_interaction(await self._store.load(cache_id))
                return _judge_verdict(cached.text), True
            except Exception:
                if self._offline:
                    raise  # the runner degrades this to an errored result
                # Unreadable cached verdict: drop it and re-ask live.
                await self._store.discard(cache_id)

        if self._offline:
            raise _OfflineMiss(model)

        adapter = adapter_for_model(model)
        conversation = Conversation(
            system=_JUDGE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": _JUDGE_TEMPLATE.format(
                        prompt=_clip(prompt),
                        baseline=_clip(baseline_text),
                        target=_clip(target_text),
                    ),
                }
            ],
            # No sampling params: the newest judge models reject them.
            max_tokens=1024,
        )
        url, headers, body = adapter.build_request(conversation, model)
        response = await self._post(url, headers, body)
        response.raise_for_status()
        payload = await response.aread()
        decoded = adapter.decode_response(payload, is_sse=False)
        verdict = _judge_verdict(decoded.text)
        if cache_id:
            # Only after the verdict parsed: a cached malformed reply would be
            # replayed as the same failure forever.
            await self._save_verdict(model, cache_id, url, headers, body, response, payload)
        return verdict, False

    async def compare(self, prompt, baseline, target) -> ComparisonResult:
        # Rendered texts (text + tool-call lines): the judge sees what each
        # model decided to do, and the cache key distinguishes differing tool
        # calls.  Identical to .text for text-only responses, so existing
        # cached verdicts stay valid.
        baseline_text = _comparable_text(baseline)
        target_text = _comparable_text(target)
        per_judge: List[Tuple[str, dict, bool]] = []
        for model in self._judge_models:
            try:
                verdict, cached = await self._verdict_for(
                    model, prompt, baseline_text, target_text
                )
            except _OfflineMiss as miss:
                return ComparisonResult(
                    comparator=self.name,
                    score=0.0,
                    passed=None,
                    detail=(
                        f"no cached verdict from judge {miss.model} for this row; "
                        "run `agentrec migrate` (online) to record one"
                    ),
                    error=True,
                )
            per_judge.append((model, verdict, cached))
        if len(per_judge) == 1:
            model, verdict, cached = per_judge[0]
            return self._result(verdict, model=model, cached=cached)
        return self._combined_result(per_judge)


@dataclass(frozen=True)
class ParsedComparator:
    """One entry of a ``--compare`` spec: a base comparator plus optional args.

    Today only ``json`` takes args (its field scope); ``name`` is the
    canonical spelling (``json:category,priority``) used as the comparator's
    display name and as the key ``--min-pass`` thresholds match against.
    """

    base: str
    args: Tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return f"{self.base}:{','.join(self.args)}" if self.args else self.base


def parse_compare_spec(spec: str) -> List[ParsedComparator]:
    """Parse ``"exact,fuzzy,json:category,priority"`` or ``"all"``.

    Comma-separated tokens; a token that is not a comparator name continues
    the argument list of the preceding ``name:...`` token, so
    ``json:category,priority`` is ONE json comparator scoped to two fields.
    (Consequence: a scoped field whose name collides with a comparator name —
    a JSON field literally called ``fuzzy`` — cannot be expressed; compare
    unscoped in that case.)  Entries are de-duplicated on their canonical
    name, so ``json`` and ``json:category`` may coexist.
    """
    if spec.strip().lower() == "all":
        return [ParsedComparator(name) for name in ALL_COMPARATOR_NAMES]

    # (base, args, scoped_form): scoped_form marks a `name:` token, whose args
    # may still be empty and whose arg list later tokens can continue.
    entries: List[Tuple[str, List[str], bool]] = []
    for token in (t.strip() for t in spec.split(",")):
        if not token:
            continue
        base, colon, first_arg = token.partition(":")
        base = base.strip().lower()
        if base in ALL_COMPARATOR_NAMES:
            if colon and base != "json":
                raise ValueError(
                    f"comparator {base!r} does not take a field scope (only 'json' does)"
                )
            args = [first_arg.strip()] if first_arg.strip() else []
            entries.append((base, args, bool(colon)))
        elif entries and entries[-1][2]:
            entries[-1][1].append(token)  # continuation of the open json:… scope
        else:
            raise ValueError(
                f"unknown comparator {token!r}; expected any of "
                f"{', '.join(ALL_COMPARATOR_NAMES)} or 'all'"
            )

    parsed: List[ParsedComparator] = []
    seen: set = set()
    for base, args, scoped_form in entries:
        if scoped_form and not args:
            raise ValueError(f"'{base}:' needs at least one field, e.g. json:category")
        entry = ParsedComparator(base, tuple(args))
        if entry.name not in seen:
            seen.add(entry.name)
            parsed.append(entry)
    if not parsed:
        raise ValueError("no comparators selected")
    return parsed


def build_comparators(
    spec: str,
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    second_judge_model: Optional[str] = None,
    embedding_model: str = "text-embedding-3-small",
    fuzzy_threshold: float = 0.8,
    embedding_threshold: float = 0.8,
    http: Optional[httpx.AsyncClient] = None,
    store: Optional[InteractionStore] = None,
    offline: bool = False,
) -> List[Comparator]:
    """Build comparators from a ``--compare`` spec like ``"exact,judge"``,
    ``"json:category,priority"`` or ``"all"``.

    ``store`` enables judge-verdict caching into that corpus; ``offline=True``
    additionally forbids the judge from opening a socket (cached verdicts
    only).  ``second_judge_model`` adds a second-opinion judge (see
    :class:`JudgeComparator`).
    """
    factories = {
        "exact": lambda entry: ExactMatchComparator(),
        "fuzzy": lambda entry: FuzzyComparator(threshold=fuzzy_threshold),
        "json": lambda entry: JsonComparator(fields=entry.args or None),
        "toolcalls": lambda entry: ToolCallsComparator(),
        "embedding": lambda entry: EmbeddingComparator(
            http, model=embedding_model, threshold=embedding_threshold
        ),
        "judge": lambda entry: JudgeComparator(
            http,
            judge_model=judge_model,
            second_judge_model=second_judge_model,
            store=store,
            offline=offline,
        ),
    }
    return [factories[entry.base](entry) for entry in parse_compare_spec(spec)]
