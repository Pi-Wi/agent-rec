"""
Model-migration runner: replay every recorded prompt against a candidate model.

For each baseline cassette in the corpus (grouped by ``semantic_key`` — the
model-agnostic identity of a prompt), the runner:

1. decodes the baseline response text,
2. extracts the provider-neutral conversation from the recorded request,
3. rebuilds the request for the target model (cross-provider translation via
   the provider adapters),
4. answers it through :class:`~agentrec.transport.AutoTransport` keyed on a
   deterministic ``migration__<baseline>__to__<model>`` cassette id — so the
   target's response is recorded into the corpus once and every re-run is
   served offline from disk,
5. scores baseline vs. target with every selected comparator in one pass.

Rows are scored **concurrently**, bounded by ``concurrency``.  The identity of
the in-flight request (cassette id + lineage metadata) travels in a task-local
contextvar, so one shared transport serves all rows without races; report row
order stays deterministic regardless of completion order.

Cross-provider semantic-key continuity: semantic keys are derived from the
provider-neutral conversation, so a translated request normally hashes to the
baseline's key by construction.  The baseline's key is still pinned onto the
migration cassette's metadata (together with ``migrated_from`` and the
baseline's ``category`` tag, when present) via the transport's
``extra_metadata`` hook — belt-and-braces for requests that only key via the
generic body-hash fallback.  The on-disk invariant "same semantic_key = same
logical prompt" survives translation either way.
"""
from __future__ import annotations

import asyncio
import contextvars
import datetime as _dt
import re
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Callable, Dict, List, Optional, Tuple

import httpx

from .comparators import JUDGE_PREFIX, Comparator, ComparisonResult
from .keying import _sanitize, fingerprint_of
from .providers import (
    Conversation,
    DecodedResponse,
    DecodeError,
    MissingAPIKeyError,
    ToolCall,
    TokenUsage,
    UnsupportedRequestError,
    adapter_for_model,
    adapter_for_provider,
    conversation_of,
    decode_interaction,
    format_conversation,
    usage_of,
)
from .store import FileStore
from .transport import AutoTransport

MIGRATION_PREFIX = "migration__"

_PREVIEW_WS = re.compile(r"\s+")

# Target-call statuses worth retrying with backoff: rate limits and
# transient provider overload (529 is Anthropic's "overloaded").  431
# ("Request Header Fields Too Large") is included because the runner builds
# fresh, minimal headers per row — a 431 here is transient infrastructure
# noise, not something a different request would fix.
_RETRYABLE_STATUSES = frozenset({429, 431, 500, 502, 503, 529})


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retry *attempt*: Retry-After wins, else 1·2ⁿ."""
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass  # not the delta-seconds form; try the HTTP-date form
        try:
            when = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError):
            return float(2**attempt)  # garbage header: fall back to exponential
        if when.tzinfo is None:
            when = when.replace(tzinfo=_dt.timezone.utc)
        return max(0.0, (when - _dt.datetime.now(_dt.timezone.utc)).total_seconds())
    return float(2**attempt)

# Identity (cassette id, extra metadata) of the row currently being scored.
# Rows run as separate asyncio tasks and contextvars are task-local, so the
# shared transport's keyer resolves each request to its own row without
# shared mutable state.
_ROW_IDENTITY: contextvars.ContextVar[Tuple[str, Dict[str, object]]] = contextvars.ContextVar(
    "agentrec_migration_row_identity"
)


def migration_id_for(baseline_id: str, target_model: str) -> str:
    """Deterministic, self-describing cassette id for one migration answer."""
    return f"{MIGRATION_PREFIX}{baseline_id}__to__{_sanitize(target_model)}"


def _preview(text: str, limit: int = 80) -> str:
    flat = _PREVIEW_WS.sub(" ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _prompt_preview(conversation, limit: int = 80) -> str:
    """A scannable one-line preview of what this row actually asks.

    Previews the *last user message* — the request being answered — so rows
    that share a system prompt (the common pipeline-corpus case) don't all
    collapse to an identical ``[system] …`` prefix.  Falls back to the full
    conversation rendering only when there is no user message (e.g. a turn
    that is purely tool results).
    """
    for message in reversed(conversation.messages):
        if message.get("role") == "user" and message.get("content"):
            return _preview(message["content"], limit)
    return _preview(format_conversation(conversation), limit)


@dataclass
class RowResult:
    """Outcome for one logical prompt (one semantic_key)."""

    semantic_key: str
    baseline_id: str
    migration_id: str
    prompt_preview: str
    prompt_text: str = ""
    category: Optional[str] = None  # from the baseline's metadata, if tagged
    baseline_model: Optional[str] = None
    # ``*_text`` is the response's prose only (display); tool calls are carried
    # structured in ``*_tool_calls`` so the report can render them as a
    # distinct block instead of inlining ``[tool_call] …`` lines into the prose.
    baseline_text: str = ""
    baseline_tool_calls: Tuple[ToolCall, ...] = ()
    baseline_in_tokens: Optional[int] = None
    baseline_out_tokens: Optional[int] = None
    target_model: str = ""
    target_text: Optional[str] = None
    target_tool_calls: Tuple[ToolCall, ...] = ()
    target_in_tokens: Optional[int] = None
    target_out_tokens: Optional[int] = None
    # Full per-category token breakdown (the *_in/_out ints above are derived
    # views kept for compatibility) plus recording timestamps, so cost can be
    # priced per-row at the date the tokens were actually bought.
    baseline_usage: Optional[TokenUsage] = None
    target_usage: Optional[TokenUsage] = None
    baseline_recorded_at: Optional[str] = None
    target_recorded_at: Optional[str] = None
    # Wall-clock seconds, request sent → response finished.  The baseline's
    # comes from its cassette (recording-time provenance, like recorded_at);
    # the target's is measured live, or read from the migration cassette on
    # a cached re-run.
    baseline_latency_s: Optional[float] = None
    target_latency_s: Optional[float] = None
    # Time-to-first-chunk (TTFB), same provenance as the totals above.  Present
    # only when the call was streamed — the target now is (so its TTFB is a real
    # number), and the baseline's is present when it was recorded streaming.
    baseline_latency_first_chunk_s: Optional[float] = None
    target_latency_first_chunk_s: Optional[float] = None
    comparisons: List[ComparisonResult] = field(default_factory=list)
    status: str = "ok"  # "ok" | "skipped" | "error"
    reason: Optional[str] = None
    cached: bool = False  # target answered from the corpus, no API call
    notes: List[str] = field(default_factory=list)


@dataclass
class ComparatorAggregate:
    comparator: str
    compared: int
    passed: int
    failed: int
    errors: int
    mean_score: Optional[float]

    @property
    def pass_rate(self) -> Optional[float]:
        judged = self.passed + self.failed
        return self.passed / judged if judged else None


@dataclass(frozen=True)
class TokenTotals:
    """Output-token volume, baseline vs target, over rows where both are known."""

    rows: int
    baseline_out: int
    target_out: int

    @property
    def ratio(self) -> Optional[float]:
        """target/baseline output tokens — the verbosity (and cost) signal."""
        return self.target_out / self.baseline_out if self.baseline_out else None


@dataclass(frozen=True)
class LatencyStats:
    """Mean response latency, baseline vs target, over rows where both are known.

    Informational only — it never gates ``--strict``.  Baseline latencies are
    recording-time provenance (the network and load of whenever the cassette
    was recorded), so read the ratio as an indication, not a benchmark.

    The ``*_first_chunk_mean_s`` fields are the time-to-first-chunk (TTFB)
    means over the ``first_chunk_rows`` subset where BOTH sides were streamed
    (so the comparison is apples-to-apples); ``None`` when no row qualifies.
    """

    rows: int
    baseline_mean_s: float
    target_mean_s: float
    first_chunk_rows: int = 0
    baseline_first_chunk_mean_s: Optional[float] = None
    target_first_chunk_mean_s: Optional[float] = None

    @property
    def ratio(self) -> Optional[float]:
        """target/baseline mean latency — <1 means the target answered faster."""
        return self.target_mean_s / self.baseline_mean_s if self.baseline_mean_s else None

    @property
    def first_chunk_ratio(self) -> Optional[float]:
        """target/baseline mean TTFB — None unless both means are known."""
        if not self.baseline_first_chunk_mean_s or self.target_first_chunk_mean_s is None:
            return None
        return self.target_first_chunk_mean_s / self.baseline_first_chunk_mean_s


@dataclass(frozen=True)
class GateResult:
    """Outcome of one ``--min-pass`` threshold against a comparator's pass rate."""

    comparator: str
    threshold: float
    pass_rate: Optional[float]
    errors: int
    passed: bool
    detail: str


@dataclass(frozen=True)
class CategoryBreakdown:
    """Comparator aggregates over the ok rows of one prompt category."""

    category: str
    prompts: int
    aggregates: List[ComparatorAggregate]
    tokens: Optional[TokenTotals]
    latency: Optional[LatencyStats] = None


@dataclass
class MigrationReport:
    target_model: str
    target_provider: str
    corpus: str
    generated_at: str
    comparator_names: List[str]
    rows: List[RowResult]
    # --min-pass thresholds (comparator name → minimum pass rate); empty means
    # --strict keeps its all-or-nothing semantics.
    min_pass: Dict[str, float] = field(default_factory=dict)

    @property
    def ok_rows(self) -> List[RowResult]:
        return [row for row in self.rows if row.status == "ok"]

    @property
    def skipped_rows(self) -> List[RowResult]:
        return [row for row in self.rows if row.status == "skipped"]

    @property
    def error_rows(self) -> List[RowResult]:
        return [row for row in self.rows if row.status == "error"]

    @property
    def cached_count(self) -> int:
        return sum(1 for row in self.ok_rows if row.cached)

    @property
    def live_count(self) -> int:
        return sum(1 for row in self.ok_rows if not row.cached)

    @property
    def baseline_models(self) -> List[str]:
        return sorted({row.baseline_model for row in self.rows if row.baseline_model})

    def aggregates(self, rows: Optional[List[RowResult]] = None) -> List[ComparatorAggregate]:
        """Per-comparator aggregates over *rows* (default: all ok rows)."""
        pool = self.ok_rows if rows is None else rows
        out = []
        for name in self.comparator_names:
            results = [
                comparison
                for row in pool
                for comparison in row.comparisons
                if comparison.comparator == name
            ]
            scored = [r for r in results if not r.error]
            out.append(
                ComparatorAggregate(
                    comparator=name,
                    compared=len(scored),
                    passed=sum(1 for r in scored if r.passed is True),
                    failed=sum(1 for r in scored if r.passed is False),
                    errors=sum(1 for r in results if r.error),
                    mean_score=(sum(r.score for r in scored) / len(scored)) if scored else None,
                )
            )
        return out

    def token_totals(self, rows: Optional[List[RowResult]] = None) -> Optional[TokenTotals]:
        """Summed output tokens over rows where baseline AND target are known."""
        pool = self.ok_rows if rows is None else rows
        counted = [
            row
            for row in pool
            if row.baseline_out_tokens is not None and row.target_out_tokens is not None
        ]
        if not counted:
            return None
        return TokenTotals(
            rows=len(counted),
            baseline_out=sum(row.baseline_out_tokens for row in counted),
            target_out=sum(row.target_out_tokens for row in counted),
        )

    def latency_stats(self, rows: Optional[List[RowResult]] = None) -> Optional[LatencyStats]:
        """Mean latency over rows where baseline AND target latency are known.

        TTFB means are computed over the (possibly smaller) subset of those
        rows where both sides also carry a first-chunk time — i.e. both were
        streamed — so a non-streamed baseline simply leaves the TTFB means out
        rather than skewing them against the streamed target.
        """
        pool = self.ok_rows if rows is None else rows
        counted = [
            row
            for row in pool
            if row.baseline_latency_s is not None and row.target_latency_s is not None
        ]
        if not counted:
            return None
        ttfb = [
            row
            for row in counted
            if row.baseline_latency_first_chunk_s is not None
            and row.target_latency_first_chunk_s is not None
        ]
        return LatencyStats(
            rows=len(counted),
            baseline_mean_s=sum(row.baseline_latency_s for row in counted) / len(counted),
            target_mean_s=sum(row.target_latency_s for row in counted) / len(counted),
            first_chunk_rows=len(ttfb),
            baseline_first_chunk_mean_s=(
                sum(row.baseline_latency_first_chunk_s for row in ttfb) / len(ttfb)
            )
            if ttfb
            else None,
            target_first_chunk_mean_s=(
                sum(row.target_latency_first_chunk_s for row in ttfb) / len(ttfb)
            )
            if ttfb
            else None,
        )

    def by_category(self) -> List[CategoryBreakdown]:
        """Per-category breakdown of the ok rows.

        Empty when no row carries a ``category`` tag (the report renderers
        then omit the section).  Untagged rows in a partially-tagged corpus
        are grouped under ``(uncategorized)``.
        """
        if not any(row.category for row in self.ok_rows):
            return []
        groups: Dict[str, List[RowResult]] = {}
        for row in self.ok_rows:
            groups.setdefault(row.category or "(uncategorized)", []).append(row)
        return [
            CategoryBreakdown(
                category=category,
                prompts=len(rows),
                aggregates=self.aggregates(rows),
                tokens=self.token_totals(rows),
                latency=self.latency_stats(rows),
            )
            for category, rows in sorted(groups.items())
        ]

    @property
    def all_passed(self) -> bool:
        """True when at least one prompt was compared and nothing failed.

        Drives the CLI's ``--strict`` exit code (when no ``--min-pass``
        thresholds are set).  An all-skipped run (e.g. offline with no
        recorded migration cassettes) is *not* a pass — a CI gate that is
        green because nothing ran would be false confidence.
        """
        if not self.ok_rows:
            return False
        if self.error_rows:
            return False
        for row in self.ok_rows:
            for comparison in row.comparisons:
                if comparison.error or comparison.passed is False:
                    return False
        return True

    def gates(self) -> List[GateResult]:
        """One :class:`GateResult` per ``min_pass`` threshold (empty when none).

        A gate passes when its comparator produced no errored comparisons and
        its pass rate over the compared rows meets the threshold.  Comparators
        without a threshold are informational and produce no gate.
        """
        aggregates = {agg.comparator: agg for agg in self.aggregates()}
        out: List[GateResult] = []
        for name, threshold in self.min_pass.items():
            agg = aggregates.get(name)
            if agg is None:
                out.append(GateResult(name, threshold, None, 0, False, "comparator did not run"))
                continue
            rate = agg.pass_rate
            if agg.errors:
                passed = False
                detail = f"{agg.errors} comparator error(s)"
                if rate is not None:
                    detail += f"; pass rate {rate:.0%} ignored"
            elif rate is None:
                passed, detail = False, "no compared rows"
            else:
                passed = rate >= threshold
                detail = (
                    f"pass rate {agg.passed}/{agg.passed + agg.failed} ({rate:.0%}) "
                    f"{'>=' if passed else '<'} {threshold:.0%}"
                )
            out.append(GateResult(name, threshold, rate, agg.errors, passed, detail))
        return out

    @property
    def strict_passed(self) -> bool:
        """Drives the CLI's ``--strict`` exit code.

        With ``min_pass`` thresholds, each named comparator gates on its pass
        rate and unnamed comparators are informational; without thresholds
        this is the all-or-nothing :attr:`all_passed`.  Either way an
        all-skipped run is not a pass, and errored rows fail the gate.
        """
        if not self.min_pass:
            return self.all_passed
        if not self.ok_rows or self.error_rows:
            return False
        return all(gate.passed for gate in self.gates())


# ---------------------------------------------------------------------------
# Per-row scoring stages
# ---------------------------------------------------------------------------
# ``run_migration`` scores each row through these stages.  They are module-level
# (not closures) so each is unit-testable and the orchestrator stays small; every
# stage mutates *row* in place and signals "stop this row" by setting
# ``row.status``/``row.reason`` and returning ``None``.


def _populate_baseline(
    row: RowResult, interaction, fp
) -> Optional[Tuple[DecodedResponse, Conversation]]:
    """Decode the baseline and fill the row's ``baseline_*`` fields.

    Returns ``(baseline, conversation)`` for scoring, or ``None`` after marking
    the row skipped when the baseline can't be decoded or its request can't be
    translated to a neutral conversation.
    """
    try:
        baseline = decode_interaction(interaction)
    except DecodeError as exc:
        row.status, row.reason = "skipped", f"baseline undecodable: {exc}"
        return None
    # Prose for display; tool calls kept structured for a distinct render.
    # (Comparators score the decoded objects directly, so dropping the inlined
    # tool-call lines here doesn't change scoring or judge caching.)
    row.baseline_text = baseline.text
    row.baseline_tool_calls = tuple(baseline.tool_calls)
    row.baseline_model = baseline.model or fp.model
    row.baseline_usage = usage_of(baseline)
    row.baseline_in_tokens = row.baseline_usage.prompt_total
    row.baseline_out_tokens = row.baseline_usage.output
    recorded_at = interaction.metadata.get("recorded_at")
    row.baseline_recorded_at = recorded_at if isinstance(recorded_at, str) else None
    latency = interaction.metadata.get("latency_s")
    row.baseline_latency_s = float(latency) if isinstance(latency, (int, float)) else None
    first_chunk = interaction.metadata.get("latency_first_chunk_s")
    row.baseline_latency_first_chunk_s = (
        float(first_chunk) if isinstance(first_chunk, (int, float)) else None
    )

    try:
        conversation = conversation_of(interaction)
    except UnsupportedRequestError as exc:
        row.status, row.reason = "skipped", f"unsupported request: {exc}"
        return None
    row.prompt_text = format_conversation(conversation)
    row.prompt_preview = _prompt_preview(conversation)
    return baseline, conversation


def _note_translation_gaps(
    row: RowResult, conversation: Conversation, fp, target_adapter
) -> None:
    """Note (never silently drop) request features this target can't carry.

    ``build_request`` gates the actual emission on the same capability, so an
    OpenAI→OpenAI run carries the knobs and produces no note.
    """
    source_adapter = adapter_for_provider(fp.provider) if fp.provider else None
    cross_provider = source_adapter is None or source_adapter.name != target_adapter.name
    if cross_provider and conversation.temperature is not None:
        conversation.temperature = None
        row.notes.append("temperature dropped in cross-provider translation")
    if (
        conversation.parallel_tool_calls is not None
        and not target_adapter.carries_parallel_tool_calls()
    ):
        row.notes.append(
            f"parallel_tool_calls={conversation.parallel_tool_calls} not carried to "
            f"{target_adapter.name}; the target may parallelize tool calls differently"
        )
    if (
        conversation.tools
        and any(tool.get("strict") for tool in conversation.tools)
        and not target_adapter.carries_function_strict()
    ):
        row.notes.append(
            f"function strict-schema enforcement dropped translating to {target_adapter.name}"
        )


def _load_cached_target(row: RowResult, recorded) -> Optional[DecodedResponse]:
    """Fill ``target_*`` provenance from a cached migration cassette and decode it.

    Returns the decoded target, or ``None`` after marking the row errored when
    the recorded response can't be decoded.
    """
    row.cached = True
    target_recorded_at = recorded.metadata.get("recorded_at")
    row.target_recorded_at = target_recorded_at if isinstance(target_recorded_at, str) else None
    target_latency = recorded.metadata.get("latency_s")
    row.target_latency_s = (
        float(target_latency) if isinstance(target_latency, (int, float)) else None
    )
    target_first_chunk = recorded.metadata.get("latency_first_chunk_s")
    row.target_latency_first_chunk_s = (
        float(target_first_chunk) if isinstance(target_first_chunk, (int, float)) else None
    )
    try:
        return decode_interaction(recorded)
    except DecodeError as exc:
        row.status, row.reason = "error", (
            f"recorded migration response undecodable: {exc}; "
            f"delete cassette {row.migration_id!r} to re-record"
        )
        return None


async def _stream_target(
    client: httpx.AsyncClient,
    store: FileStore,
    row: RowResult,
    conversation: Conversation,
    target_adapter,
    target_model: str,
    *,
    max_tokens_default: int,
    retries: int,
) -> Optional[DecodedResponse]:
    """Build, stream and decode the live target call, with retry/backoff.

    Streaming gives a real time-to-first-chunk (comparable to a streamed
    baseline's); the AutoTransport tees the chunks into the corpus and the
    response is re-decoded by content type, so a target that ignores ``stream``
    and answers with a JSON body still decodes.  Sets the row's target
    latency/TTFB on success.  Returns the decoded target, or ``None`` after
    marking the row skipped/errored.
    """
    try:
        url, headers, body = target_adapter.build_request(
            conversation, target_model, max_tokens_default=max_tokens_default, stream=True,
        )
    except MissingAPIKeyError as exc:
        row.status, row.reason = "error", str(exc)
        return None
    except UnsupportedRequestError as exc:
        # The target dialect can't faithfully represent this request (e.g. a
        # strict json_schema, or tool-call arguments that never parsed to an
        # object).  An honest skipped row — not a crash — mirrors the
        # extract-time skip handled in _populate_baseline.
        row.status, row.reason = "skipped", f"target cannot represent request: {exc}"
        return None

    # Per-row identity (cassette id + lineage) rides a contextvar the shared
    # transport's keyer reads; pin the baseline's semantic_key onto the cassette.
    extra: Dict[str, object] = {
        "migrated_from": row.baseline_id,
        "semantic_key": row.semantic_key,
        "baseline_model": row.baseline_model,
    }
    if row.category:
        extra["category"] = row.category
    _ROW_IDENTITY.set((row.migration_id, extra))

    payload = b""
    is_sse = False
    for attempt in range(max(0, retries) + 1):
        attempt_start = time.monotonic()
        first_chunk_at: Optional[float] = None
        try:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code == 200:
                    buffer = bytearray()
                    async for chunk in response.aiter_bytes():
                        if first_chunk_at is None and chunk:
                            first_chunk_at = time.monotonic()
                        buffer.extend(chunk)
                    payload = bytes(buffer)
                    is_sse = "text/event-stream" in response.headers.get(
                        "content-type", ""
                    ).lower()
                else:
                    payload = await response.aread()
        except httpx.HTTPError as exc:
            row.status, row.reason = "error", f"target call failed: {exc}"
            return None
        if response.status_code == 200:
            done = time.monotonic()
            row.target_latency_s = round(done - attempt_start, 4)
            row.target_latency_first_chunk_s = round((first_chunk_at or done) - attempt_start, 4)
            break
        # Don't let a failure poison the cache: the transport recorded this
        # response, so discard it before any retry or re-run.
        await store.discard(row.migration_id)
        if response.status_code in _RETRYABLE_STATUSES and attempt < retries:
            row.notes.append(
                f"retried after HTTP {response.status_code} (attempt {attempt + 1}/{retries})"
            )
            await asyncio.sleep(_retry_delay(response, attempt))
            continue
        row.status, row.reason = "error", (
            f"target API returned {response.status_code}: "
            f"{payload[:200].decode('utf-8', 'replace')}"
        )
        return None

    try:
        return target_adapter.decode_response(payload, is_sse=is_sse)
    except DecodeError as exc:
        row.status, row.reason = "error", f"target response undecodable: {exc}"
        return None


def _populate_target(row: RowResult, target: DecodedResponse, target_model: str) -> None:
    """Fill the row's ``target_*`` fields and flag a token-cap truncation."""
    row.target_text = target.text
    row.target_tool_calls = tuple(target.tool_calls)
    row.target_model = target.model or target_model
    row.target_usage = usage_of(target)
    row.target_in_tokens = row.target_usage.prompt_total
    row.target_out_tokens = row.target_usage.output
    if target.finish_reason in ("max_tokens", "length"):
        # A truncated target makes every comparison (and the output-token ratio)
        # quietly unfair — surface it instead of letting the numbers lie.
        row.notes.append(
            f"target response was truncated by its token cap "
            f"(finish_reason={target.finish_reason!r}); scores and token "
            "ratios may be skewed — consider raising --max-tokens"
        )


async def _score_comparisons(
    row: RowResult, comparators: List[Comparator], baseline: DecodedResponse, target: DecodedResponse
) -> None:
    """Score the row with every comparator in one pass; degrade, never crash."""
    for comparator in comparators:
        try:
            row.comparisons.append(
                await comparator.compare(row.prompt_text, baseline, target)
            )
        except Exception as exc:
            row.comparisons.append(
                ComparisonResult(
                    comparator=comparator.name,
                    score=0.0,
                    passed=None,
                    detail=f"comparator failed: {exc}",
                    error=True,
                )
            )


async def run_migration(
    store: FileStore,
    target_model: str,
    comparators: List[Comparator],
    *,
    target_provider: Optional[str] = None,
    offline: bool = False,
    max_tokens_default: int = 4096,
    filter_substr: Optional[str] = None,
    inner_transport: Optional[httpx.AsyncBaseTransport] = None,
    concurrency: int = 8,
    retries: int = 3,
    progress: Optional[Callable[[RowResult], None]] = None,
    min_pass: Optional[Dict[str, float]] = None,
) -> MigrationReport:
    """Compare every corpus prompt's recorded answer against *target_model*.

    Rows are scored concurrently (bounded by ``concurrency``); report row
    order stays deterministic regardless of completion order, and ``progress``
    is invoked once per finished row.  A rate-limited or overloaded target
    call (429/5xx) is retried up to ``retries`` times with backoff, honouring
    ``Retry-After``.  ``offline=True`` never opens a socket: prompts without a
    recorded migration cassette become skipped rows.  ``inner_transport``
    overrides the real network transport (test seam).  ``min_pass`` carries
    per-comparator pass-rate thresholds into the report (see
    :meth:`MigrationReport.gates`).
    """
    target_adapter = (
        adapter_for_provider(target_provider) if target_provider else adapter_for_model(target_model)
    )

    # Migration answers and cached judge verdicts live in the same corpus but
    # are tooling artifacts, not prompts to compare.
    baseline_ids = [
        bid
        for bid in store.ids()
        if not bid.startswith(MIGRATION_PREFIX) and not bid.startswith(JUDGE_PREFIX)
    ]
    if filter_substr:
        baseline_ids = [bid for bid in baseline_ids if filter_substr in bid]

    # Group baselines by semantic_key: one report row per logical prompt.
    groups: Dict[str, list] = {}
    for baseline_id in baseline_ids:
        interaction = await store.load(baseline_id)
        fp = fingerprint_of(interaction)
        groups.setdefault(fp.semantic_key, []).append((baseline_id, interaction, fp))

    # One AutoTransport/client for the whole run; each task pins its row's
    # identity in _ROW_IDENTITY before posting, and the keyer reads it back.
    transport = AutoTransport(
        inner_transport or httpx.AsyncHTTPTransport(),
        store,
        key=lambda request: _ROW_IDENTITY.get()[0],
        extra_metadata=lambda request: dict(_ROW_IDENTITY.get()[1]),
    )
    client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(120.0))
    semaphore = asyncio.Semaphore(max(1, concurrency))

    rows: List[RowResult] = []
    jobs: List[tuple] = []
    for semantic_key, group in groups.items():
        # Newest recording wins when the same prompt was recorded twice.
        group.sort(key=lambda item: (item[1].metadata.get("recorded_at") or "", item[0]))
        baseline_id, interaction, fp = group[-1]
        category = interaction.metadata.get("category")
        row = RowResult(
            semantic_key=semantic_key,
            baseline_id=baseline_id,
            migration_id=migration_id_for(baseline_id, target_model),
            prompt_preview="",
            category=category if isinstance(category, str) else None,
            baseline_model=fp.model,
            target_model=target_model,
        )
        if len(group) > 1:
            row.notes.append(
                "older recordings of this prompt ignored: "
                + ", ".join(item[0] for item in group[:-1])
            )
        rows.append(row)
        jobs.append((row, interaction, fp))

    async def score_row(row: RowResult, interaction, fp) -> None:
        populated = _populate_baseline(row, interaction, fp)
        if populated is None:
            return  # baseline undecodable or untranslatable — row already marked
        baseline, conversation = populated
        _note_translation_gaps(row, conversation, fp, target_adapter)

        # Target: replay a cached migration answer, skip (offline, none cached),
        # or stream a live one through the shared AutoTransport.
        if await store.has(row.migration_id):
            target = _load_cached_target(row, await store.load(row.migration_id))
        elif offline:
            row.status, row.reason = "skipped", (
                "no recorded migration response; run `agentrec migrate` (online) first"
            )
            return
        else:
            target = await _stream_target(
                client, store, row, conversation, target_adapter, target_model,
                max_tokens_default=max_tokens_default, retries=retries,
            )
        if target is None:
            return  # a stage marked the row skipped/errored

        _populate_target(row, target, target_model)
        await _score_comparisons(row, comparators, baseline, target)

    async def bounded(row: RowResult, interaction, fp) -> None:
        async with semaphore:
            await score_row(row, interaction, fp)
        if progress is not None:
            progress(row)

    try:
        await asyncio.gather(*(bounded(*job) for job in jobs))
    finally:
        await client.aclose()

    return MigrationReport(
        target_model=target_model,
        target_provider=target_adapter.name,
        corpus=str(getattr(store, "root", "")),
        generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        comparator_names=[comparator.name for comparator in comparators],
        rows=rows,
        min_pass=dict(min_pass or {}),
    )


async def annotate_corpus(store: FileStore) -> List[str]:
    """Backfill summary blocks and fingerprint metadata into every cassette.

    Loads and re-saves each cassette: saving regenerates the human-readable
    ``summary`` block, and missing metadata is recomputed from the stored
    request.  ``setdefault`` keeps pinned values (e.g. a migration cassette's
    baseline ``semantic_key``) intact.  Returns the annotated ids.
    """
    annotated: List[str] = []
    for interaction_id in store.ids():
        interaction = await store.load(interaction_id)
        try:
            fp = fingerprint_of(interaction)
            for key, value in fp.as_metadata().items():
                interaction.metadata.setdefault(key, value)
        except Exception:
            pass
        await store.save(interaction_id, interaction)
        annotated.append(interaction_id)
    return annotated