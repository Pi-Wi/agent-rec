"""
Pricing tests: token-usage normalization, snapshot loading/validation,
date-based snapshot selection, Decimal cost math, report pricing, rendering,
and the CLI flags — fully offline.

The contracts under test: tokens are the canonical recorded metric and cost
is derived; pricing snapshots are immutable dated files with provenance
(sha256) in the report; an estimate with unpriced token categories is marked
incomplete instead of silently free; and totals only sum rows where both
sides priced completely.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agentrec import (
    FileStore,
    PricingCatalog,
    PricingError,
    PricingProfile,
    PricingSnapshot,
    TokenUsage,
    build_comparators,
    price_report,
    run_migration,
)
from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.cli import main as cli_main
from agentrec.providers import AnthropicAdapter, OpenAIAdapter, generic_token_usage
from agentrec.report import render_console, render_html, render_markdown

TARGET_MODEL = "claude-haiku-4-5"
PROMPT = "Classify the dominant color in 'a clear summer sky': answer with one word."


# ---------------------------------------------------------------------------
# TokenUsage normalization
# ---------------------------------------------------------------------------


def test_openai_usage_normalization_disentangles_cached_and_reasoning():
    # OpenAI: prompt_tokens INCLUDES cached, completion_tokens INCLUDES reasoning.
    usage = OpenAIAdapter().normalize_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens_details": {"reasoning_tokens": 10},
        }
    )
    assert usage.input == 60  # uncached only — disjoint from cache_read
    assert usage.cache_read == 40
    assert usage.cache_write is None
    assert usage.output == 50  # reasoning stays inside output
    assert usage.reasoning == 10
    assert usage.prompt_total == 100
    assert usage.raw["prompt_tokens"] == 100  # verbatim dict preserved


def test_anthropic_usage_normalization_is_already_disjoint():
    # Anthropic: input_tokens EXCLUDES cache traffic; fields map directly.
    usage = AnthropicAdapter().normalize_usage(
        {
            "input_tokens": 7,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 20,
            "output_tokens": 3,
        }
    )
    assert (usage.input, usage.cache_read, usage.cache_write, usage.output) == (7, 100, 20, 3)
    assert usage.prompt_total == 127


def test_usage_normalization_tolerates_missing_and_partial_data():
    empty = OpenAIAdapter().normalize_usage(None)
    assert empty == TokenUsage()
    assert empty.prompt_total is None

    # No details block: cached is unknown, input falls back to the full prompt.
    plain = OpenAIAdapter().normalize_usage({"prompt_tokens": 7, "completion_tokens": 3})
    assert (plain.input, plain.cache_read, plain.output) == (7, None, 3)
    assert plain.prompt_total == 7

    generic = generic_token_usage({"prompt_tokens": 5, "output_tokens": 2})
    assert (generic.input, generic.output) == (5, 2)


# ---------------------------------------------------------------------------
# Snapshot loading, validation, resolution
# ---------------------------------------------------------------------------


def _snapshot_dict(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "profile": "test-list",
        "currency": "USD",
        "effective": "2026-01-01",
        "models": [
            {
                "match": ["gpt-4o-mini", "gpt-4o-mini-*"],
                "unit": "per_mtok",
                "rates": {"input": "0.15", "cache_read": "0.075", "output": "0.60"},
            },
            {
                "match": ["claude-haiku-4-5", "claude-haiku-4-5-*"],
                "unit": "per_mtok",
                "rates": {"input": "1", "cache_read": "0.10", "cache_write": "1.25", "output": "5"},
            },
        ],
    }
    data.update(overrides)
    return data


def test_snapshot_validation_rejects_defects():
    with pytest.raises(PricingError, match="schema_version"):
        PricingSnapshot.from_dict(_snapshot_dict(schema_version=2))
    with pytest.raises(PricingError, match="currency"):
        PricingSnapshot.from_dict(_snapshot_dict(currency=""))
    with pytest.raises(PricingError, match="effective"):
        PricingSnapshot.from_dict(_snapshot_dict(effective="June 2026"))
    with pytest.raises(PricingError, match="unknown rate category"):
        PricingSnapshot.from_dict(
            _snapshot_dict(models=[{"match": ["m"], "rates": {"inptu": "1"}}])
        )
    with pytest.raises(PricingError, match="negative"):
        PricingSnapshot.from_dict(
            _snapshot_dict(models=[{"match": ["m"], "rates": {"input": "-1"}}])
        )
    # Tiered (long-context) pricing is schema-reserved but unevaluated: honest failure.
    with pytest.raises(PricingError, match="tiers"):
        PricingSnapshot.from_dict(
            _snapshot_dict(
                models=[{"match": ["m"], "rates": {"input": "1"}, "tiers": [{}]}]
            )
        )
    # The same exact model id in two entries is ambiguous within one snapshot.
    with pytest.raises(PricingError, match="already matched"):
        PricingSnapshot.from_dict(
            _snapshot_dict(
                models=[
                    {"match": ["m"], "rates": {"input": "1"}},
                    {"match": ["m"], "rates": {"input": "2"}},
                ]
            )
        )


def test_snapshot_resolution_exact_beats_glob_and_handles_date_suffixes():
    snapshot = PricingSnapshot.from_dict(
        _snapshot_dict(
            models=[
                {"match": ["gpt-4o-*"], "rates": {"input": "9"}},
                {"match": ["gpt-4o-mini"], "rates": {"input": "0.15"}},
            ]
        )
    )
    entry, matched = snapshot.resolve("gpt-4o-mini")
    assert matched == "gpt-4o-mini"  # exact wins even though the glob comes first
    assert entry.per_mtok["input"] == Decimal("0.15")

    entry, matched = snapshot.resolve("gpt-4o-mini-2024-07-18")  # dated id → glob
    assert matched == "gpt-4o-*"
    assert snapshot.resolve("claude-haiku-4-5") is None  # unknown model: no rate, never zero


def test_profile_selects_snapshot_by_effective_date():
    cheap = PricingSnapshot.from_dict(_snapshot_dict(effective="2026-01-01"))
    pricey = PricingSnapshot.from_dict(
        _snapshot_dict(
            effective="2026-06-01",
            models=[{"match": ["gpt-4o-mini"], "rates": {"input": "0.30", "output": "1.20"}}],
        )
    )
    profile = PricingProfile("test-list", [pricey, cheap])  # order in, sorted internally

    on_march = profile.resolve("gpt-4o-mini", dt.date(2026, 3, 1))
    assert on_march.per_mtok["input"] == Decimal("0.15")
    on_july = profile.resolve("gpt-4o-mini", dt.date(2026, 7, 1))
    assert on_july.per_mtok["input"] == Decimal("0.30")
    latest = profile.resolve("gpt-4o-mini", None)
    assert latest.per_mtok["input"] == Decimal("0.30")
    # Before the first snapshot: oldest wins (old corpora stay priceable).
    ancient = profile.resolve("gpt-4o-mini", dt.date(2020, 1, 1))
    assert ancient.per_mtok["input"] == Decimal("0.15")


def test_cost_is_exact_decimal_and_flags_unpriced_categories():
    profile = PricingProfile("p", [PricingSnapshot.from_dict(_snapshot_dict())])
    rate = profile.resolve("gpt-4o-mini")

    # 1M input tokens at $0.15/MTok is exactly $0.15 — no float drift.
    exact = rate.cost(TokenUsage(input=1_000_000))
    assert exact.total == Decimal("0.15")
    assert exact.complete

    # cache_write tokens have no rate in this entry → incomplete, not free.
    partial = rate.cost(TokenUsage(input=10, cache_write=100, output=2))
    assert partial.unpriced == ("cache_write",)
    assert not partial.complete
    assert partial.total == (Decimal("0.15") * 10 + Decimal("0.60") * 2) / Decimal(1_000_000)

    assert rate.cost(None) is None
    assert rate.cost(TokenUsage()) is None  # nothing known → no estimate, not $0
    # Provenance travels with every estimate.
    assert exact.rate_ref.profile == "p"
    assert len(exact.rate_ref.digest) == 64


def test_catalog_builtin_profiles_and_user_shadowing(tmp_path: Path):
    builtin = PricingCatalog.default()
    assert {"anthropic-list", "openai-list"} <= set(builtin.profile_names)
    assert builtin.profile("anthropic-list").resolve("claude-haiku-4-5") is not None
    assert builtin.profile("openai-list").resolve("gpt-4o-mini-2024-07-18") is not None

    # A user profile named like a built-in replaces it entirely.
    override = tmp_path / "openai-list"
    override.mkdir()
    (override / "2026-01-01.json").write_text(
        json.dumps(
            _snapshot_dict(
                profile="openai-list",
                models=[{"match": ["custom-model"], "rates": {"input": "1"}}],
            )
        ),
        encoding="utf-8",
    )
    catalog = PricingCatalog.load(tmp_path)
    assert catalog.profile("openai-list").resolve("custom-model") is not None
    assert catalog.profile("openai-list").resolve("gpt-4o-mini") is None  # built-in gone
    assert catalog.profile("anthropic-list").resolve("claude-haiku-4-5") is not None

    with pytest.raises(LookupError, match="no pricing profile"):
        catalog.profile("does-not-exist")


def test_composite_profile_spans_providers():
    catalog = PricingCatalog.default()
    combined = catalog.profile("anthropic-list+openai-list")
    assert combined.resolve("claude-haiku-4-5") is not None
    assert combined.resolve("gpt-4o-mini") is not None
    assert combined.name == "anthropic-list+openai-list"


# ---------------------------------------------------------------------------
# Pricing a real migration report (offline, mirrors test_migration fixtures)
# ---------------------------------------------------------------------------


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _openai_chunk(content=None, finish=None) -> dict:
    delta = {"content": content} if content is not None else {}
    return {
        "id": "chatcmpl-x",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _baseline_interaction() -> CapturedInteraction:
    body = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": PROMPT}]}
    final = _openai_chunk(None, finish="stop")
    final["usage"] = {"prompt_tokens": 7, "completion_tokens": 3}
    return CapturedInteraction(
        request=CapturedRequest(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers=[(b"content-type", b"application/json")],
            content=json.dumps(body).encode(),
        ),
        response_status=200,
        response_headers=[(b"content-type", b"text/event-stream; charset=utf-8")],
        response_extensions={},
        chunks=[CapturedChunk(data=_sse(_openai_chunk(part))) for part in ("bl", "ue")]
        + [CapturedChunk(data=_sse(final)), CapturedChunk(data=b"data: [DONE]\n\n")],
    )


def _anthropic_answer(text: str = "Blue") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": TARGET_MODEL,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 2},
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def corpus(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "corpus")


async def _migrated_report(corpus: FileStore, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    interaction = _baseline_interaction()
    interaction.metadata["category"] = "classify"
    interaction.metadata["recorded_at"] = "2026-03-15T12:00:00+00:00"
    await corpus.save("ticket-color", interaction)
    return await run_migration(
        corpus, TARGET_MODEL, build_comparators("exact"), inner_transport=_anthropic_answer()
    )


def _test_profile() -> PricingProfile:
    return PricingProfile("test-list", [PricingSnapshot.from_dict(_snapshot_dict())])


async def test_price_report_end_to_end(corpus: FileStore, monkeypatch):
    report = await _migrated_report(corpus, monkeypatch)
    row = report.rows[0]
    # The runner kept the full per-category usage alongside the int columns.
    assert row.baseline_usage.prompt_total == 7 and row.baseline_usage.output == 3
    assert row.target_usage.input == 12 and row.target_usage.output == 2
    assert row.baseline_recorded_at == "2026-03-15T12:00:00+00:00"

    pricing = price_report(report, _test_profile())
    cost = pricing.row_cost(row)
    # gpt-4o-mini: 7 in * 0.15 + 3 out * 0.60 per MTok; haiku: 12 * 1 + 2 * 5.
    assert cost.baseline.total == Decimal("0.00000285")
    assert cost.target.total == Decimal("0.000022")
    assert cost.complete

    totals = pricing.totals(report.ok_rows)
    assert totals.rows == 1
    assert totals.baseline_total == Decimal("0.00000285")
    assert totals.target_total == Decimal("0.000022")
    assert totals.ratio == pytest.approx(float(Decimal("0.000022") / Decimal("0.00000285")))
    # Provenance: the snapshot used is named with its digest.
    assert [ref.snapshot for ref in pricing.snapshots] == ["test-list@2026-01-01"]


async def test_price_report_as_of_recorded_uses_cassette_dates(corpus: FileStore, monkeypatch):
    report = await _migrated_report(corpus, monkeypatch)
    cheap = PricingSnapshot.from_dict(_snapshot_dict(effective="2026-01-01"))
    pricey = PricingSnapshot.from_dict(
        _snapshot_dict(
            effective="2099-01-01",
            models=[
                {"match": ["gpt-4o-mini"], "rates": {"input": "1.50", "output": "6"}},
                {"match": ["claude-haiku-4-5"], "rates": {"input": "10", "output": "50"}},
            ],
        )
    )
    profile = PricingProfile("test-list", [cheap, pricey])

    # recorded_at = 2026-03-15 → the 2026 snapshot, not the 2099 one.
    recorded = price_report(report, profile, as_of="recorded")
    assert recorded.row_cost(report.rows[0]).baseline.total == Decimal("0.00000285")
    # latest → the newest snapshot, 10x the rates.
    latest = price_report(report, profile, as_of="latest")
    assert latest.row_cost(report.rows[0]).baseline.total == Decimal("0.0000285")
    # Pinned date reproduces a historical view.
    pinned = price_report(report, profile, as_of="2026-02-01")
    assert pinned.row_cost(report.rows[0]).baseline.total == Decimal("0.00000285")
    assert pinned.as_of == "2026-02-01"

    with pytest.raises(PricingError, match="as_of"):
        price_report(report, profile, as_of="next tuesday")


async def test_unpriced_models_and_incomplete_rows_never_count_in_totals(
    corpus: FileStore, monkeypatch
):
    report = await _migrated_report(corpus, monkeypatch)
    # Profile only knows the baseline model: the target gets no estimate, the
    # row is incomplete, and totals refuse to sum it — no one-sided "savings".
    half = PricingProfile(
        "half",
        [
            PricingSnapshot.from_dict(
                _snapshot_dict(
                    profile="half",
                    models=[{"match": ["gpt-4o-mini"], "rates": {"input": "0.15", "output": "0.60"}}],
                )
            )
        ],
    )
    pricing = price_report(report, half)
    cost = pricing.row_cost(report.rows[0])
    assert cost.baseline is not None and cost.target is None
    assert not cost.complete
    assert pricing.totals(report.ok_rows) is None


async def test_renderers_show_cost_and_provenance(corpus: FileStore, monkeypatch):
    report = await _migrated_report(corpus, monkeypatch)
    pricing = price_report(report, _test_profile())

    markdown = render_markdown(report, pricing=[pricing])
    assert "| Est. cost (test-list) |" in markdown  # consolidated totals table
    assert "Cost (test-list)" in markdown  # per-row column
    assert "## Pricing" in markdown
    assert "test-list@2026-01-01" in markdown
    assert pricing.snapshots[0].digest[:12] in markdown

    html = render_html(report, pricing=[pricing])
    assert "Est. cost (test-list)" in html
    assert "Pricing" in html and pricing.snapshots[0].digest[:12] in html

    console = render_console(report, pricing=[pricing])
    assert console.isascii(), "console output must be ASCII-safe on Windows terminals"
    assert "est. cost (test-list)" in console
    assert "$" in console

    # Without pricing the report is unchanged (tokens stay the canonical metric).
    assert "Est. cost" not in render_markdown(report)


def test_cli_report_with_pricing_flags(corpus: FileStore, monkeypatch, tmp_path: Path, capsys):
    asyncio.run(_migrated_report(corpus, monkeypatch))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    pricing_dir = tmp_path / "pricing" / "test-list"
    pricing_dir.mkdir(parents=True)
    (pricing_dir / "2026-01-01.json").write_text(json.dumps(_snapshot_dict()), encoding="utf-8")

    out_base = tmp_path / "rep"
    code = cli_main(
        [
            "report",
            "--corpus", str(corpus.root),
            "--target", TARGET_MODEL,
            "--compare", "exact",
            "--format", "md",
            "--out", str(out_base),
            "--pricing", "test-list",
            "--pricing-dir", str(tmp_path / "pricing"),
            "--pricing-as-of", "recorded",
        ]
    )
    assert code == 0
    assert "est. cost (test-list)" in capsys.readouterr().out
    markdown = (tmp_path / "rep.md").read_text(encoding="utf-8")
    assert "Est. cost (test-list)" in markdown and "## Pricing" in markdown

    # Unknown profile and bad as-of are usage errors (exit 2), not crashes.
    base = ["report", "--corpus", str(corpus.root), "--target", TARGET_MODEL,
            "--compare", "exact", "--format", "md", "--out", str(out_base)]
    assert cli_main(base + ["--pricing", "nope"]) == 2
    assert cli_main(base + ["--pricing", "anthropic-list", "--pricing-as-of", "soon"]) == 2
