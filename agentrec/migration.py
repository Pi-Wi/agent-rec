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

Cross-provider semantic-key continuity: a translated request body hashes to a
different semantic key, so the baseline's key is pinned onto the migration
cassette's metadata (together with ``migrated_from`` and the baseline's
``category`` tag, when present) via the transport's ``extra_metadata`` hook.
The on-disk invariant "same semantic_key = same logical prompt" survives
translation.
"""
from __future__ import annotations

import asyncio
import contextvars
import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import httpx

from .comparators import Comparator, ComparisonResult
from .keying import _sanitize, fingerprint_of
from .providers import (
    DecodeError,
    MissingAPIKeyError,
    UnsupportedRequestError,
    adapter_for_model,
    adapter_for_provider,
    conversation_of,
    decode_interaction,
    format_conversation,
)
from .store import FileStore
from .transport import AutoTransport

MIGRATION_PREFIX = "migration__"

_PREVIEW_WS = re.compile(r"\s+")

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


def _usage_tokens(usage: Optional[dict]) -> Tuple[Optional[int], Optional[int]]:
    """(input, output) token counts from an OpenAI- or Anthropic-shaped usage dict."""
    if not isinstance(usage, dict):
        return None, None

    def first_int(*keys: str) -> Optional[int]:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int):
                return value
        return None

    return (
        first_int("input_tokens", "prompt_tokens"),
        first_int("output_tokens", "completion_tokens"),
    )


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
    baseline_text: str = ""
    baseline_in_tokens: Optional[int] = None
    baseline_out_tokens: Optional[int] = None
    target_model: str = ""
    target_text: Optional[str] = None
    target_in_tokens: Optional[int] = None
    target_out_tokens: Optional[int] = None
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
class CategoryBreakdown:
    """Comparator aggregates over the ok rows of one prompt category."""

    category: str
    prompts: int
    aggregates: List[ComparatorAggregate]
    tokens: Optional[TokenTotals]


@dataclass
class MigrationReport:
    target_model: str
    target_provider: str
    corpus: str
    generated_at: str
    comparator_names: List[str]
    rows: List[RowResult]

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
            )
            for category, rows in sorted(groups.items())
        ]

    @property
    def all_passed(self) -> bool:
        """True when nothing failed: drives the CLI's ``--strict`` exit code."""
        if self.error_rows:
            return False
        for row in self.ok_rows:
            for comparison in row.comparisons:
                if comparison.error or comparison.passed is False:
                    return False
        return True


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
    progress: Optional[Callable[[RowResult], None]] = None,
) -> MigrationReport:
    """Compare every corpus prompt's recorded answer against *target_model*.

    Rows are scored concurrently (bounded by ``concurrency``); report row
    order stays deterministic regardless of completion order, and ``progress``
    is invoked once per finished row.  ``offline=True`` never opens a socket:
    prompts without a recorded migration cassette become skipped rows.
    ``inner_transport`` overrides the real network transport (test seam).
    """
    target_adapter = (
        adapter_for_provider(target_provider) if target_provider else adapter_for_model(target_model)
    )

    baseline_ids = [bid for bid in store.ids() if not bid.startswith(MIGRATION_PREFIX)]
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
        # --- Baseline ---------------------------------------------------
        try:
            baseline = decode_interaction(interaction)
        except DecodeError as exc:
            row.status, row.reason = "skipped", f"baseline undecodable: {exc}"
            return
        row.baseline_text = baseline.text
        row.baseline_model = baseline.model or fp.model
        row.baseline_in_tokens, row.baseline_out_tokens = _usage_tokens(baseline.usage)

        try:
            conversation = conversation_of(interaction)
        except UnsupportedRequestError as exc:
            row.status, row.reason = "skipped", f"unsupported request: {exc}"
            return
        row.prompt_text = format_conversation(conversation)
        row.prompt_preview = _preview(row.prompt_text)

        source_adapter = adapter_for_provider(fp.provider) if fp.provider else None
        cross_provider = source_adapter is None or source_adapter.name != target_adapter.name
        if cross_provider and conversation.temperature is not None:
            conversation.temperature = None
            row.notes.append("temperature dropped in cross-provider translation")

        # --- Target (cache, or live via the shared AutoTransport) --------
        target = None
        if await store.has(row.migration_id):
            row.cached = True
            try:
                target = decode_interaction(await store.load(row.migration_id))
            except DecodeError as exc:
                row.status, row.reason = "error", (
                    f"recorded migration response undecodable: {exc}; "
                    f"delete cassette {row.migration_id!r} to re-record"
                )
                return
        elif offline:
            row.status, row.reason = "skipped", (
                "no recorded migration response; run `agentrec migrate` (online) first"
            )
            return
        else:
            try:
                url, headers, body = target_adapter.build_request(
                    conversation, target_model, max_tokens_default=max_tokens_default
                )
            except MissingAPIKeyError as exc:
                row.status, row.reason = "error", str(exc)
                return
            extra: Dict[str, object] = {
                "migrated_from": row.baseline_id,
                "semantic_key": row.semantic_key,  # pin the baseline's key
                "baseline_model": row.baseline_model,
            }
            if row.category:
                extra["category"] = row.category
            _ROW_IDENTITY.set((row.migration_id, extra))
            try:
                response = await client.post(url, headers=headers, json=body)
                payload = await response.aread()
            except httpx.HTTPError as exc:
                row.status, row.reason = "error", f"target call failed: {exc}"
                return
            if response.status_code != 200:
                # Don't let a failure poison the cache: a re-run retries.
                await store.discard(row.migration_id)
                row.status, row.reason = "error", (
                    f"target API returned {response.status_code}: "
                    f"{payload[:200].decode('utf-8', 'replace')}"
                )
                return
            try:
                target = target_adapter.decode_response(payload, is_sse=False)
            except DecodeError as exc:
                row.status, row.reason = "error", f"target response undecodable: {exc}"
                return

        row.target_text = target.text
        row.target_model = target.model or target_model
        row.target_in_tokens, row.target_out_tokens = _usage_tokens(target.usage)

        # --- Score with every comparator in one pass ---------------------
        for comparator in comparators:
            try:
                row.comparisons.append(
                    await comparator.compare(row.prompt_text, baseline, target)
                )
            except Exception as exc:  # degrade, never crash the run
                row.comparisons.append(
                    ComparisonResult(
                        comparator=comparator.name,
                        score=0.0,
                        passed=None,
                        detail=f"comparator failed: {exc}",
                        error=True,
                    )
                )

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