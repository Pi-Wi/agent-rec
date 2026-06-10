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

Cross-provider semantic-key continuity: a translated request body hashes to a
different semantic key, so the baseline's key is pinned onto the migration
cassette's metadata (together with ``migrated_from``) via the transport's
``extra_metadata`` hook.  The on-disk invariant "same semantic_key = same
logical prompt" survives translation.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
from .store import FileStore, InteractionStore
from .transport import AutoTransport

MIGRATION_PREFIX = "migration__"

_PREVIEW_WS = re.compile(r"\s+")


def migration_id_for(baseline_id: str, target_model: str) -> str:
    """Deterministic, self-describing cassette id for one migration answer."""
    return f"{MIGRATION_PREFIX}{baseline_id}__to__{_sanitize(target_model)}"


def _preview(text: str, limit: int = 80) -> str:
    flat = _PREVIEW_WS.sub(" ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


@dataclass
class RowResult:
    """Outcome for one logical prompt (one semantic_key)."""

    semantic_key: str
    baseline_id: str
    migration_id: str
    prompt_preview: str
    prompt_text: str = ""
    baseline_model: Optional[str] = None
    baseline_text: str = ""
    target_model: str = ""
    target_text: Optional[str] = None
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

    def aggregates(self) -> List[ComparatorAggregate]:
        out = []
        for name in self.comparator_names:
            results = [
                comparison
                for row in self.ok_rows
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
) -> MigrationReport:
    """Compare every corpus prompt's recorded answer against *target_model*.

    ``offline=True`` never opens a socket: prompts without a recorded
    migration cassette become skipped rows.  ``inner_transport`` overrides the
    real network transport (test seam).
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

    # One AutoTransport/client for the whole run; per-row identity flows
    # through this mutable state (the keyer/extra_metadata consult it).
    state: dict = {"id": "", "extra": {}}
    transport = AutoTransport(
        inner_transport or httpx.AsyncHTTPTransport(),
        store,
        key=lambda request: state["id"],
        extra_metadata=lambda request: dict(state["extra"]),
    )
    client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(120.0))

    rows: List[RowResult] = []
    try:
        for semantic_key, group in groups.items():
            # Newest recording wins when the same prompt was recorded twice.
            group.sort(key=lambda item: (item[1].metadata.get("recorded_at") or "", item[0]))
            baseline_id, interaction, fp = group[-1]
            row = RowResult(
                semantic_key=semantic_key,
                baseline_id=baseline_id,
                migration_id=migration_id_for(baseline_id, target_model),
                prompt_preview="",
                baseline_model=fp.model,
                target_model=target_model,
            )
            if len(group) > 1:
                row.notes.append(
                    "older recordings of this prompt ignored: "
                    + ", ".join(item[0] for item in group[:-1])
                )
            rows.append(row)

            # --- Baseline ---------------------------------------------------
            try:
                baseline = decode_interaction(interaction)
            except DecodeError as exc:
                row.status, row.reason = "skipped", f"baseline undecodable: {exc}"
                continue
            row.baseline_text = baseline.text
            row.baseline_model = baseline.model or fp.model

            try:
                conversation = conversation_of(interaction)
            except UnsupportedRequestError as exc:
                row.status, row.reason = "skipped", f"unsupported request: {exc}"
                continue
            row.prompt_text = format_conversation(conversation)
            row.prompt_preview = _preview(row.prompt_text)

            source_adapter = adapter_for_provider(fp.provider) if fp.provider else None
            cross_provider = source_adapter is None or source_adapter.name != target_adapter.name
            if cross_provider and conversation.temperature is not None:
                conversation.temperature = None
                row.notes.append("temperature dropped in cross-provider translation")

            # --- Target (cache, or live via AutoTransport) -------------------
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
                    continue
            elif offline:
                row.status, row.reason = "skipped", (
                    "no recorded migration response; run `agentrec migrate` (online) first"
                )
                continue
            else:
                try:
                    url, headers, body = target_adapter.build_request(
                        conversation, target_model, max_tokens_default=max_tokens_default
                    )
                except MissingAPIKeyError as exc:
                    row.status, row.reason = "error", str(exc)
                    continue
                state["id"] = row.migration_id
                state["extra"] = {
                    "migrated_from": baseline_id,
                    "semantic_key": semantic_key,  # pin the baseline's key
                    "baseline_model": row.baseline_model,
                }
                try:
                    response = await client.post(url, headers=headers, json=body)
                    payload = await response.aread()
                except httpx.HTTPError as exc:
                    row.status, row.reason = "error", f"target call failed: {exc}"
                    continue
                if response.status_code != 200:
                    # Don't let a failure poison the cache: a re-run retries.
                    await store.discard(row.migration_id)
                    row.status, row.reason = "error", (
                        f"target API returned {response.status_code}: "
                        f"{payload[:200].decode('utf-8', 'replace')}"
                    )
                    continue
                try:
                    target = target_adapter.decode_response(payload, is_sse=False)
                except DecodeError as exc:
                    row.status, row.reason = "error", f"target response undecodable: {exc}"
                    continue

            row.target_text = target.text
            row.target_model = target.model or target_model

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
