"""
Versioned pricing snapshots and derived cost estimates for migration reports.

Tokens are the canonical recorded metric — they live in the cassettes and
never change.  Cost is **always derived at report time** from a
:class:`~agentrec.providers.TokenUsage` and a dated, immutable pricing
snapshot; nothing about cost is ever written into a cassette.  Because every
estimate carries the snapshot's digest, a historical report can name exactly
which prices produced its numbers, and re-pricing the same
:class:`~agentrec.migration.MigrationReport` against several profiles
("official list" vs. "our enterprise contract") costs nothing.

Concepts:

* **Snapshot** — one immutable JSON file of per-model, per-category rates,
  valid from its ``effective`` date.  A price change is a *new* dated file,
  never an edit (the sha256 digest in report provenance makes mutation
  detectable).
* **Profile** — a named series of snapshots over time ("openai-list",
  "acme-enterprise").  Resolution picks the newest snapshot whose
  ``effective`` date is on or before the pricing date.
* **Catalog** — profiles discovered from the built-in package data plus any
  user directories; a user profile with a built-in's name shadows it.
* :func:`price_report` — attaches per-row :class:`CostEstimate` pairs to a
  finished migration report.  ``as_of="latest"`` (default) prices both models
  at the newest snapshot — the forward-looking migration question;
  ``"recorded"`` prices each row at its cassette's ``recorded_at`` — the
  "what did this corpus actually cost" question; an explicit date pins a
  historical report.

Rates are Decimal (money in floats drifts); a token category with traffic
but no rate makes the estimate *incomplete* rather than silently free, and
totals only sum rows where both sides priced completely — a target must not
look cheap because half its rows were unpriceable.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import fnmatch
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from .migration import MigrationReport, RowResult
from .providers import TokenUsage

#: Token categories a rate may price, in (disjoint) TokenUsage terms.
#: ``reasoning`` is deliberately absent: it is a subset of ``output``.
PRICED_CATEGORIES = ("input", "cache_read", "cache_write", "output")

_BUILTIN_DIR = Path(__file__).parent / "pricing_data"

_MTOK = Decimal(1_000_000)


class PricingError(ValueError):
    """A pricing snapshot is malformed or a pricing option is invalid."""


# ---------------------------------------------------------------------------
# Snapshot loading & validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRate:
    """Per-MTok rates for the models matched by ``match`` (exact ids or globs)."""

    match: Tuple[str, ...]
    per_mtok: Mapping[str, Decimal]


@dataclass(frozen=True)
class RateRef:
    """Provenance of one resolved rate — enough to reproduce the estimate."""

    profile: str
    snapshot: str  # e.g. "openai-list/2026-06-12.json" or "openai-list@2026-06-12"
    effective: str  # ISO date the snapshot is valid from
    digest: str  # sha256 of the snapshot content
    matched: str  # the match entry that selected the model


@dataclass(frozen=True)
class CostEstimate:
    """Derived cost of one response's tokens under one resolved rate."""

    total: Decimal
    currency: str
    by_category: Mapping[str, Decimal]
    unpriced: Tuple[str, ...]  # categories with tokens but no rate
    rate_ref: RateRef

    @property
    def complete(self) -> bool:
        return not self.unpriced


@dataclass(frozen=True)
class ResolvedRate:
    """A model's rates under one snapshot, ready to price token usage."""

    per_mtok: Mapping[str, Decimal]
    currency: str
    ref: RateRef

    def cost(self, usage: Optional[TokenUsage]) -> Optional[CostEstimate]:
        """Price *usage*, or ``None`` when no token counts are known at all.

        Categories with tokens but no rate are reported in ``unpriced``
        (the estimate renders as incomplete) instead of pricing as zero.
        """
        if usage is None:
            return None
        by_category: Dict[str, Decimal] = {}
        unpriced: List[str] = []
        any_tokens = False
        for category in PRICED_CATEGORIES:
            count = getattr(usage, category)
            if not count:  # None or 0: nothing to price in this bucket
                continue
            any_tokens = True
            rate = self.per_mtok.get(category)
            if rate is None:
                unpriced.append(category)
            else:
                by_category[category] = (rate * count) / _MTOK
        if not any_tokens:
            return None
        return CostEstimate(
            total=sum(by_category.values(), Decimal(0)),
            currency=self.currency,
            by_category=by_category,
            unpriced=tuple(unpriced),
            rate_ref=self.ref,
        )


def _parse_rates(raw: object, *, where: str) -> Mapping[str, Decimal]:
    if not isinstance(raw, dict) or not raw:
        raise PricingError(f"{where}: 'rates' must be a non-empty object")
    rates: Dict[str, Decimal] = {}
    for category, value in raw.items():
        if category not in PRICED_CATEGORIES:
            raise PricingError(
                f"{where}: unknown rate category {category!r} "
                f"(expected any of: {', '.join(PRICED_CATEGORIES)})"
            )
        try:
            rate = Decimal(str(value))
        except InvalidOperation:
            raise PricingError(f"{where}: rate for {category!r} is not a number: {value!r}") from None
        if rate < 0:
            raise PricingError(f"{where}: rate for {category!r} is negative")
        rates[category] = rate
    return rates


class PricingSnapshot:
    """One immutable, dated set of per-model rates for a profile."""

    def __init__(
        self,
        *,
        profile: str,
        currency: str,
        effective: _dt.date,
        models: List[ModelRate],
        digest: str,
        name: str,
        source: Optional[str] = None,
    ) -> None:
        self.profile = profile
        self.currency = currency
        self.effective = effective
        self.models = models
        self.digest = digest
        self.name = name
        self.source = source

    @classmethod
    def from_dict(cls, data: dict, *, name: Optional[str] = None) -> "PricingSnapshot":
        """Parse and validate a snapshot; raises :class:`PricingError` on any defect."""
        if not isinstance(data, dict):
            raise PricingError("snapshot must be a JSON object")
        where = name or "<dict>"
        if data.get("schema_version") != 1:
            raise PricingError(f"{where}: unsupported schema_version {data.get('schema_version')!r}")
        profile = data.get("profile")
        if not isinstance(profile, str) or not profile:
            raise PricingError(f"{where}: 'profile' must be a non-empty string")
        currency = data.get("currency")
        if not isinstance(currency, str) or not currency:
            raise PricingError(f"{where}: 'currency' must be a non-empty string")
        try:
            effective = _dt.date.fromisoformat(str(data.get("effective")))
        except ValueError:
            raise PricingError(f"{where}: 'effective' must be an ISO date (YYYY-MM-DD)") from None

        entries = data.get("models")
        if not isinstance(entries, list) or not entries:
            raise PricingError(f"{where}: 'models' must be a non-empty list")
        models: List[ModelRate] = []
        exact_seen: Dict[str, int] = {}
        for index, entry in enumerate(entries):
            entry_where = f"{where}: models[{index}]"
            if not isinstance(entry, dict):
                raise PricingError(f"{entry_where}: must be an object")
            if entry.get("tiers"):
                # Honest failure beats silently wrong numbers: tiered
                # (long-context) pricing is schema-reserved but not evaluated.
                raise PricingError(f"{entry_where}: 'tiers' are not supported yet")
            unit = entry.get("unit", "per_mtok")
            if unit != "per_mtok":
                raise PricingError(f"{entry_where}: unsupported unit {unit!r}")
            match = entry.get("match")
            if (
                not isinstance(match, list)
                or not match
                or not all(isinstance(m, str) and m for m in match)
            ):
                raise PricingError(f"{entry_where}: 'match' must be a non-empty list of strings")
            for pattern in match:
                if not _is_glob(pattern):
                    if pattern in exact_seen:
                        raise PricingError(
                            f"{entry_where}: model id {pattern!r} already matched by "
                            f"models[{exact_seen[pattern]}]"
                        )
                    exact_seen[pattern] = index
            models.append(
                ModelRate(match=tuple(match), per_mtok=_parse_rates(entry.get("rates"), where=entry_where))
            )

        digest = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            profile=profile,
            currency=currency,
            effective=effective,
            models=models,
            digest=digest,
            name=name or f"{profile}@{effective.isoformat()}",
            source=data.get("source") if isinstance(data.get("source"), str) else None,
        )

    @classmethod
    def from_file(cls, path: Path) -> "PricingSnapshot":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise PricingError(f"{path}: not valid JSON: {exc}") from None
        snapshot = cls.from_dict(data, name=f"{path.parent.name}/{path.name}")
        return snapshot

    def resolve(self, model: str) -> Optional[Tuple[ModelRate, str]]:
        """(rate, matched-pattern) for *model*: exact ids first, then globs in file order."""
        for entry in self.models:
            for pattern in entry.match:
                if not _is_glob(pattern) and pattern == model:
                    return entry, pattern
        for entry in self.models:
            for pattern in entry.match:
                if _is_glob(pattern) and fnmatch.fnmatchcase(model, pattern):
                    return entry, pattern
        return None


def _is_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[")


# ---------------------------------------------------------------------------
# Profiles & catalog
# ---------------------------------------------------------------------------


class PricingProfile:
    """A named series of snapshots; resolution picks the snapshot for a date."""

    def __init__(self, name: str, snapshots: Sequence[PricingSnapshot]) -> None:
        if not snapshots:
            raise PricingError(f"profile {name!r} has no snapshots")
        currencies = {snapshot.currency for snapshot in snapshots}
        if len(currencies) > 1:
            raise PricingError(
                f"profile {name!r} mixes currencies: {', '.join(sorted(currencies))} "
                "(one currency per profile; use a separate profile per currency)"
            )
        self.name = name
        self.currency = snapshots[0].currency
        # Oldest → newest; effective-date ties broken by name for determinism.
        self.snapshots = sorted(snapshots, key=lambda s: (s.effective, s.name))

    def snapshot_for(self, on: Optional[_dt.date]) -> PricingSnapshot:
        """Newest snapshot effective on/before *on*; ``None`` means the newest.

        A date before the first snapshot falls back to the oldest one —
        a corpus older than the price history should still be priceable
        (the provenance in the report shows the snapshot date used).
        """
        if on is None:
            return self.snapshots[-1]
        chosen = self.snapshots[0]
        for snapshot in self.snapshots:
            if snapshot.effective <= on:
                chosen = snapshot
        return chosen

    def resolve(self, model: str, on: Optional[_dt.date] = None) -> Optional[ResolvedRate]:
        """Rates for *model* at date *on* (``None`` = newest snapshot), or None."""
        snapshot = self.snapshot_for(on)
        found = snapshot.resolve(model)
        if found is None:
            return None
        entry, matched = found
        return ResolvedRate(
            per_mtok=entry.per_mtok,
            currency=snapshot.currency,
            ref=RateRef(
                profile=self.name,
                snapshot=snapshot.name,
                effective=snapshot.effective.isoformat(),
                digest=snapshot.digest,
                matched=matched,
            ),
        )


class CompositeProfile:
    """Several profiles tried in order — e.g. ``anthropic-list+openai-list``.

    Lets one ``--pricing`` spec price a cross-provider migration from the
    per-provider list-price profiles without maintaining a merged file.
    All member profiles must share a currency.
    """

    def __init__(self, profiles: Sequence[PricingProfile]) -> None:
        if not profiles:
            raise PricingError("composite profile needs at least one member")
        currencies = {profile.currency for profile in profiles}
        if len(currencies) > 1:
            raise PricingError(
                "composite profile mixes currencies: " + ", ".join(sorted(currencies))
            )
        self.profiles = list(profiles)
        self.name = "+".join(profile.name for profile in profiles)
        self.currency = profiles[0].currency

    def resolve(self, model: str, on: Optional[_dt.date] = None) -> Optional[ResolvedRate]:
        for profile in self.profiles:
            resolved = profile.resolve(model, on)
            if resolved is not None:
                return resolved
        return None


class PricingCatalog:
    """Profiles discovered from built-in package data plus user directories."""

    def __init__(self, profiles: Mapping[str, PricingProfile]) -> None:
        self._profiles = dict(profiles)

    @classmethod
    def default(cls) -> "PricingCatalog":
        """Only the snapshots shipped with the package."""
        return cls(_load_dir(_BUILTIN_DIR))

    @classmethod
    def load(cls, *directories: "str | Path", include_builtin: bool = True) -> "PricingCatalog":
        """Built-in profiles plus *directories* (later wins, whole-profile shadowing).

        A directory holds ``<profile>/<date>.json`` snapshot files (any
        ``*.json`` below it works — files are grouped by their ``profile``
        field).  A user profile named like a built-in replaces it entirely,
        so a company can pin its own "anthropic-list" without partial merges.
        """
        profiles: Dict[str, PricingProfile] = dict(_load_dir(_BUILTIN_DIR)) if include_builtin else {}
        for directory in directories:
            profiles.update(_load_dir(Path(directory)))
        return cls(profiles)

    @property
    def profile_names(self) -> List[str]:
        return sorted(self._profiles)

    def profile(self, spec: str) -> "PricingProfile | CompositeProfile":
        """Profile by name; ``a+b`` composes several, tried left to right."""
        names = [name.strip() for name in spec.split("+") if name.strip()]
        if not names:
            raise LookupError(f"empty pricing profile spec {spec!r}")
        members = []
        for name in names:
            if name not in self._profiles:
                known = ", ".join(self.profile_names) or "<none>"
                raise LookupError(f"no pricing profile named {name!r} (known: {known})")
            members.append(self._profiles[name])
        if len(members) == 1:
            return members[0]
        return CompositeProfile(members)


def _load_dir(directory: Path) -> Dict[str, PricingProfile]:
    if not directory.is_dir():
        return {}
    grouped: Dict[str, List[PricingSnapshot]] = {}
    for path in sorted(directory.rglob("*.json")):
        snapshot = PricingSnapshot.from_file(path)
        grouped.setdefault(snapshot.profile, []).append(snapshot)
    return {name: PricingProfile(name, snapshots) for name, snapshots in grouped.items()}


# ---------------------------------------------------------------------------
# Pricing a migration report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RowCost:
    """Baseline/target estimate pair for one report row (either may be None)."""

    baseline: Optional[CostEstimate]
    target: Optional[CostEstimate]

    @property
    def complete(self) -> bool:
        return (
            self.baseline is not None
            and self.target is not None
            and self.baseline.complete
            and self.target.complete
        )


@dataclass(frozen=True)
class CostTotals:
    """Summed cost over rows where BOTH sides priced completely."""

    rows: int
    currency: str
    baseline_total: Decimal
    target_total: Decimal

    @property
    def ratio(self) -> Optional[float]:
        """target/baseline cost — the headline migration signal."""
        return float(self.target_total / self.baseline_total) if self.baseline_total else None


@dataclass
class ReportPricing:
    """One profile's cost view of a migration report, with provenance."""

    profile: str
    currency: str
    as_of: str  # the policy used: "latest" | "recorded" | an ISO date
    rows: Dict[str, RowCost]  # semantic_key → estimates
    snapshots: List[RateRef] = field(default_factory=list)  # deduped, matched=""

    def row_cost(self, row: RowResult) -> Optional[RowCost]:
        return self.rows.get(row.semantic_key)

    def totals(self, rows: Sequence[RowResult]) -> Optional[CostTotals]:
        """Totals over *rows*; only rows whose both sides priced completely count.

        Mixed-completeness sums are the subtle lie to avoid — a target must
        not look cheap because half its rows had no rate.
        """
        counted = [
            cost
            for row in rows
            if (cost := self.rows.get(row.semantic_key)) is not None and cost.complete
        ]
        if not counted:
            return None
        return CostTotals(
            rows=len(counted),
            currency=self.currency,
            baseline_total=sum((c.baseline.total for c in counted), Decimal(0)),
            target_total=sum((c.target.total for c in counted), Decimal(0)),
        )


def _date_of(timestamp: Optional[str]) -> Optional[_dt.date]:
    if not timestamp:
        return None
    try:
        return _dt.datetime.fromisoformat(timestamp).date()
    except ValueError:
        return None


def price_report(
    report: MigrationReport,
    profile: "PricingProfile | CompositeProfile",
    *,
    as_of: Union[str, _dt.date] = "latest",
) -> ReportPricing:
    """Derive per-row cost estimates for *report* under *profile*.

    ``as_of`` selects the snapshot date policy:

    * ``"latest"`` (default) — both models priced at the newest snapshot, on
      one consistent date: the forward-looking "what would each model cost
      going forward" question a migration decision asks.
    * ``"recorded"`` — each response priced at its cassette's ``recorded_at``
      date (falling back to the report's ``generated_at``): historical
      "what did this actually cost" accuracy across price changes.
    * a :class:`datetime.date` or ``"YYYY-MM-DD"`` string — pinned, for
      reproducing an old report exactly.

    Cassettes are never touched: tokens stay the canonical metric and the
    same report can be priced against any number of profiles.
    """
    if isinstance(as_of, _dt.date):
        policy, fixed = as_of.isoformat(), as_of
    elif as_of in ("latest", "recorded"):
        policy, fixed = as_of, None
    else:
        try:
            fixed = _dt.date.fromisoformat(str(as_of))
        except ValueError:
            raise PricingError(
                f"as_of must be 'latest', 'recorded' or an ISO date, got {as_of!r}"
            ) from None
        policy = fixed.isoformat()

    generated_date = _date_of(report.generated_at)

    def pricing_date(recorded_at: Optional[str]) -> Optional[_dt.date]:
        if policy == "latest":
            return None  # newest snapshot
        if policy == "recorded":
            return _date_of(recorded_at) or generated_date
        return fixed

    rows: Dict[str, RowCost] = {}
    refs: Dict[str, RateRef] = {}

    def estimate(
        model: Optional[str], usage: Optional[TokenUsage], recorded_at: Optional[str]
    ) -> Optional[CostEstimate]:
        if not model or usage is None:
            return None
        resolved = profile.resolve(model, pricing_date(recorded_at))
        if resolved is None:
            return None
        cost = resolved.cost(usage)
        if cost is not None:
            ref = cost.rate_ref
            refs.setdefault(ref.snapshot, dataclasses.replace(ref, matched=""))
        return cost

    for row in report.ok_rows:
        rows[row.semantic_key] = RowCost(
            baseline=estimate(row.baseline_model, row.baseline_usage, row.baseline_recorded_at),
            target=estimate(row.target_model, row.target_usage, row.target_recorded_at),
        )

    return ReportPricing(
        profile=profile.name,
        currency=profile.currency,
        as_of=policy,
        rows=rows,
        snapshots=sorted(refs.values(), key=lambda ref: ref.snapshot),
    )
