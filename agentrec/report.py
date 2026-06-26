"""
Render a :class:`~agentrec.migration.MigrationReport` for humans.

* ``render_markdown`` — one consolidated summary (verdict table + totals),
  per-category breakdown, per-prompt results table, collapsible details
  (failures first, capped).
* ``render_html``     — self-contained single file (inline CSS, no JS) with
  color-coded scores, the category breakdown and side-by-side panels; the
  primary artifact.
* ``render_console``  — a few ASCII-safe lines for the terminal.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .keying import _sanitize
from .migration import ComparatorAggregate, MigrationReport, RowResult
from .pricing import ReportPricing
from .providers.base import _fmt_tool_arguments

#: Renderers accept one ReportPricing or a list (one cost view per profile).
PricingArg = Optional[Union[ReportPricing, Sequence[ReportPricing]]]

#: Default cap on per-row Details entries before the rest are summarised.
DEFAULT_MAX_DETAIL_ROWS = 25


def _pricing_list(pricing: PricingArg) -> List[ReportPricing]:
    if pricing is None:
        return []
    if isinstance(pricing, ReportPricing):
        return [pricing]
    return list(pricing)


def _rows_by_category(report: MigrationReport) -> Dict[str, List[RowResult]]:
    groups: Dict[str, List[RowResult]] = {}
    for row in report.ok_rows:
        groups.setdefault(row.category or "(uncategorized)", []).append(row)
    return groups


def default_report_basename(target_model: str, when: Optional[_dt.datetime] = None) -> str:
    when = when or _dt.datetime.now()
    return f"migration-report__{_sanitize(target_model)}__{when.strftime('%Y%m%d-%H%M%S')}"


def _fmt_score(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.2f}"


def _fmt_rate(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.0%}"


def _fmt_ratio(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.2f}×"


def _fmt_money(value: Decimal, currency: str) -> str:
    """``$0.0042`` — up to 6 decimals, trailing zeros trimmed to at least 2."""
    text = format(value.quantize(Decimal("0.000001")), ",f")
    whole, _, frac = text.partition(".")
    frac = frac.rstrip("0").ljust(2, "0")
    amount = f"{whole}.{frac}"
    return f"${amount}" if currency == "USD" else f"{amount} {currency}"


def _fmt_cost_cell(pricing: ReportPricing, row: RowResult) -> str:
    """Per-row cost cell, e.g. ``$0.0021→$0.0008`` (`*` = incomplete estimate)."""
    cost = pricing.row_cost(row)
    if cost is None or (cost.baseline is None and cost.target is None):
        return "–"

    def one(estimate) -> str:
        if estimate is None:
            return "?"
        return _fmt_money(estimate.total, estimate.currency) + ("" if estimate.complete else "*")

    return f"{one(cost.baseline)}→{one(cost.target)}"


def _pricing_summary(
    pricing: ReportPricing, report: MigrationReport, *, arrow: str = "→", times: str = "×"
) -> str:
    """One-line baseline→target cost totals for a profile (ASCII-safe via args)."""
    totals = pricing.totals(report.ok_rows)
    if totals is None:
        return f"est. cost ({pricing.profile}): no rows priced"
    ratio = "" if totals.ratio is None else f"{totals.ratio:.2f}{times}, "
    return (
        f"est. cost ({pricing.profile}): "
        f"baseline {_fmt_money(totals.baseline_total, totals.currency)} {arrow} "
        f"target {_fmt_money(totals.target_total, totals.currency)} "
        f"({ratio}over {totals.rows} priced rows)"
    )


def _fmt_out_tokens(row: RowResult) -> str:
    """Per-row output-token cell, e.g. ``12→34`` ('–' when nothing is known)."""
    if row.baseline_out_tokens is None and row.target_out_tokens is None:
        return "–"
    baseline = "?" if row.baseline_out_tokens is None else str(row.baseline_out_tokens)
    target = "?" if row.target_out_tokens is None else str(row.target_out_tokens)
    return f"{baseline}→{target}"


def _fmt_seconds(value: Optional[float]) -> str:
    return "?" if value is None else f"{value:.2f}s"


def _fmt_latency(row: RowResult) -> str:
    """Per-row latency cell, e.g. ``2.41s→0.87s`` ('–' when nothing is known)."""
    if row.baseline_latency_s is None and row.target_latency_s is None:
        return "–"
    return f"{_fmt_seconds(row.baseline_latency_s)}→{_fmt_seconds(row.target_latency_s)}"


def _fmt_first_chunk(row: RowResult) -> str:
    """Per-row TTFB cell, e.g. ``0.30s→0.12s`` ('–' when nothing is known)."""
    if (
        row.baseline_latency_first_chunk_s is None
        and row.target_latency_first_chunk_s is None
    ):
        return "–"
    return (
        f"{_fmt_seconds(row.baseline_latency_first_chunk_s)}"
        f"→{_fmt_seconds(row.target_latency_first_chunk_s)}"
    )


_LATENCY_CAVEAT = (
    "Baseline latencies are recording-time provenance (whenever each cassette "
    "was recorded); read the ratio as an indication, not a benchmark."
)


def _totals_rows(
    report: MigrationReport, pricings: List[ReportPricing]
) -> Tuple[List[Tuple[str, str, str, str]], bool]:
    """Rows for the consolidated totals table: (metric, baseline, target, ratio).

    Returns the rows plus whether a latency row is present (the caller appends
    the recording-time caveat only then).
    """
    rows: List[Tuple[str, str, str, str]] = []
    totals = report.token_totals()
    if totals:
        rows.append(
            ("Output tokens", f"{totals.baseline_out:,}", f"{totals.target_out:,}",
             _fmt_ratio(totals.ratio))
        )
    latency = report.latency_stats()
    if latency:
        rows.append(
            ("Latency (mean)", _fmt_seconds(latency.baseline_mean_s),
             _fmt_seconds(latency.target_mean_s), _fmt_ratio(latency.ratio))
        )
        # TTFB only when both sides streamed (the runner streams targets, so
        # this appears whenever the baseline was recorded streaming too).
        if latency.first_chunk_rows and latency.baseline_first_chunk_mean_s is not None:
            rows.append(
                ("TTFB (mean)", _fmt_seconds(latency.baseline_first_chunk_mean_s),
                 _fmt_seconds(latency.target_first_chunk_mean_s),
                 _fmt_ratio(latency.first_chunk_ratio))
            )
    for entry in pricings:
        cost_totals = entry.totals(report.ok_rows)
        if cost_totals is None:
            rows.append((f"Est. cost ({entry.profile})", "–", "–", "no rows priced"))
        else:
            rows.append((
                f"Est. cost ({entry.profile})",
                _fmt_money(cost_totals.baseline_total, cost_totals.currency),
                _fmt_money(cost_totals.target_total, cost_totals.currency),
                _fmt_ratio(cost_totals.ratio),
            ))
    return rows, latency is not None


def _row_failed(row: RowResult) -> bool:
    return any(c.error or c.passed is False for c in row.comparisons)


def _row_mean(row: RowResult) -> float:
    scores = [c.score for c in row.comparisons if c.score is not None]
    return sum(scores) / len(scores) if scores else 0.0


def _ordered_detail_rows(rows: List[RowResult]) -> List[Tuple[int, RowResult]]:
    """``(original_index, row)`` pairs, failing rows first then lowest mean score.

    The index keeps detail headers aligned with the Results table, while the
    ordering floats the rows worth reading to the top of a capped Details list.
    """
    return sorted(
        enumerate(rows, 1),
        key=lambda item: (0 if _row_failed(item[1]) else 1, _row_mean(item[1])),
    )


def _comparison_cell(row: RowResult, name: str) -> str:
    for comparison in row.comparisons:
        if comparison.comparator == name:
            if comparison.error:
                return "⚠️ error"
            mark = {True: "✅", False: "❌", None: ""}[comparison.passed]
            return f"{mark} {comparison.score:.2f}".strip()
    return "–"


def _aggregate_cell(agg: ComparatorAggregate) -> str:
    """Compact per-category cell: pass rate and mean score."""
    return f"{_fmt_rate(agg.pass_rate)} · {_fmt_score(agg.mean_score)}"


# ---------------------------------------------------------------------------
# Shared table model
# ---------------------------------------------------------------------------
# The migration report's five tables (summary, totals, gate, by-category,
# results) used to be built twice — once as Markdown, once as HTML — so adding a
# column meant editing both renderers in lockstep.  A table is now built once as
# a grid of :class:`Cell`s; ``_md_table`` / ``_html_table`` are the only
# format-specific plumbing.  A cell can carry distinct Markdown and HTML forms
# (e.g. a category renders as plain text in Markdown, a ``<span class='tag'>``
# chip in HTML) and an optional HTML ``<td>`` CSS class (pass/fail shading), so
# the per-format cell decorations survive a single shared column layout.


@dataclass(frozen=True)
class Cell:
    """One table cell: its Markdown text, its HTML body, and an optional td class."""

    md: str
    html: str
    cls: str = ""

    def td(self) -> str:
        return f"<td class='{self.cls}'>{self.html}</td>" if self.cls else f"<td>{self.html}</td>"

    def th(self) -> str:
        return f"<th>{self.html}</th>"


def _cell(value: str, *, cls: str = "") -> Cell:
    """A plain cell whose Markdown and HTML forms are *value*, escaped per format."""
    return Cell(md=_md_escape_cell(value), html=_html.escape(value), cls=cls)


@dataclass
class Table:
    headers: List[Cell]
    rows: List[List[Cell]]
    aligns: List[str]  # one Markdown alignment token ("---" / "---:") per column


def _md_table(table: Table) -> List[str]:
    """Markdown lines for *table* (header, alignment row, body rows)."""
    lines = ["| " + " | ".join(c.md for c in table.headers) + " |"]
    lines.append("|" + "|".join(table.aligns) + "|")
    for row in table.rows:
        lines.append("| " + " | ".join(c.md for c in row) + " |")
    return lines


def _html_table(table: Table) -> str:
    """A ``<table>…</table>`` string for *table*."""
    parts = ["<table><tr>", *(c.th() for c in table.headers), "</tr>"]
    for row in table.rows:
        parts.append("<tr>")
        parts.extend(c.td() for c in row)
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def _summary_table(report: MigrationReport) -> Table:
    """Per-comparator verdict table (passed / pass rate / mean score)."""
    rows: List[List[Cell]] = []
    for agg in report.aggregates():
        passed = "–" if agg.pass_rate is None else f"{agg.passed}/{agg.passed + agg.failed}"
        rows.append([
            _cell(agg.comparator), _cell(passed),
            _cell(_fmt_rate(agg.pass_rate)), _cell(_fmt_score(agg.mean_score)),
        ])
    return Table(
        headers=[_cell("Comparator"), _cell("Passed"), _cell("Pass rate"), _cell("Mean score")],
        rows=rows,
        aligns=["---", "---:", "---:", "---:"],
    )


def _totals_table(report: MigrationReport, pricings: List[ReportPricing]) -> Tuple[Optional[Table], bool]:
    """Baseline→target totals (tokens / latency / TTFB / cost); ``None`` when empty.

    Returns ``(table, has_latency)`` — the caller appends the recording-time
    latency caveat only when a latency row is present.
    """
    rows_data, has_latency = _totals_rows(report, pricings)
    if not rows_data:
        return None, has_latency
    table = Table(
        headers=[_cell("Metric"), _cell("Baseline"), _cell("Target"), _cell("Ratio")],
        rows=[[_cell(metric), _cell(base), _cell(target), _cell(ratio)]
              for metric, base, target, ratio in rows_data],
        aligns=["---", "---:", "---:", "---:"],
    )
    return table, has_latency


def _gate_table(report: MigrationReport) -> Table:
    """``--min-pass`` gate outcomes; the verdict cell carries pass/fail shading."""
    rows: List[List[Cell]] = []
    for gate in report.gates():
        word = "pass" if gate.passed else "fail"
        mark = "✅ pass" if gate.passed else "❌ fail"
        verdict = Cell(
            md=f"{mark} — {_md_escape_cell(gate.detail)}",
            html=f"{word} — {_html.escape(gate.detail)}",
            cls=word,
        )
        rows.append([
            _cell(gate.comparator), _cell(_fmt_rate(gate.threshold)),
            _cell(_fmt_rate(gate.pass_rate)), _cell(str(gate.errors)), verdict,
        ])
    return Table(
        headers=[_cell("Comparator"), _cell("Threshold"), _cell("Pass rate"),
                 _cell("Errors"), _cell("Verdict")],
        rows=rows,
        aligns=["---", "---:", "---:", "---:", "---"],
    )


def _category_cell(category: str) -> Cell:
    """A category label: plain text in Markdown, a pill chip in HTML."""
    return Cell(md=category, html=f"<span class='tag'>{_html.escape(category)}</span>")


def _category_table(
    report: MigrationReport,
    breakdown: List,
    pricings: List[ReportPricing],
    category_rows: Dict[str, List[RowResult]],
) -> Table:
    """Per-category pass-rate · mean-score grid, with token/latency/cost ratios."""
    headers = [_cell("Category"), _cell("Prompts")]
    headers += [_cell(name) for name in report.comparator_names]
    headers += [_cell("Out tokens"), _cell("Latency")]
    headers += [_cell(f"Cost ({entry.profile})") for entry in pricings]
    rows: List[List[Cell]] = []
    for cat in breakdown:
        cells = [_category_cell(cat.category), _cell(str(cat.prompts))]
        cells += [_cell(_aggregate_cell(agg)) for agg in cat.aggregates]
        cells.append(_cell(_fmt_ratio(cat.tokens.ratio) if cat.tokens else "–"))
        cells.append(_cell(_fmt_ratio(cat.latency.ratio) if cat.latency else "–"))
        for entry in pricings:
            cost_totals = entry.totals(category_rows.get(cat.category, []))
            cells.append(_cell(_fmt_ratio(cost_totals.ratio) if cost_totals else "–"))
        rows.append(cells)
    return Table(headers=headers, rows=rows, aligns=["---"] + ["---:"] * (len(headers) - 1))


def _prompt_cell(row: RowResult) -> Cell:
    """The Results-table prompt preview, flagged when the step involves tools."""
    tools = _has_tool_calls(row)
    md = _md_escape_cell(row.prompt_preview)
    html = _html.escape(row.prompt_preview)
    return Cell(
        md=f"🔧 {md}" if tools else md,
        html=f"{html} <span class='tag'>tools</span>" if tools else html,
    )


def _verdict_cell(row: RowResult, name: str) -> Cell:
    """A per-row comparator result cell, shaded pass/fail/error in HTML."""
    text = _comparison_cell(row, name)
    return Cell(md=text, html=_html.escape(text), cls=_html_cell_class(row, name))


def _results_table(
    report: MigrationReport, breakdown: List, pricings: List[ReportPricing]
) -> Table:
    """One row per compared prompt: previews, per-comparator marks, tokens, cost."""
    headers = [_cell("#"), _cell("Prompt")]
    if breakdown:
        headers.append(_cell("Category"))
    # Markdown says "Baseline model"; HTML's narrower column says "Baseline".
    headers.append(Cell(md="Baseline model", html="Baseline"))
    headers += [_cell(name) for name in report.comparator_names]
    headers += [_cell("Out tok"), _cell("Latency")]
    headers += [_cell(f"Cost ({entry.profile})") for entry in pricings]
    headers.append(_cell("Cached"))

    rows: List[List[Cell]] = []
    for index, row in enumerate(report.ok_rows, 1):
        cells = [_cell(str(index)), _prompt_cell(row)]
        if breakdown:
            cells.append(_category_cell(row.category) if row.category else _cell("–"))
        cells.append(_cell(row.baseline_model or "?"))
        cells += [_verdict_cell(row, name) for name in report.comparator_names]
        cells.append(_cell(_fmt_out_tokens(row)))
        cells.append(_cell(_fmt_latency(row)))
        cells += [_cell(_fmt_cost_cell(entry, row)) for entry in pricings]
        cells.append(Cell(md="✅" if row.cached else "live", html="yes" if row.cached else "live"))
        rows.append(cells)
    return Table(headers=headers, rows=rows, aligns=["---"] * len(headers))


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _md_escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _md_fence(text: str) -> str:
    # Widen the fence if the text itself contains backtick runs.
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}text\n{text}\n{fence}"


def _has_tool_calls(row: RowResult) -> bool:
    return bool(row.baseline_tool_calls or row.target_tool_calls)


def _md_tool_calls(calls) -> List[str]:
    """A bullet per tool call: ``- `name`(args)`` (canonical arg rendering)."""
    return [
        f"- `{_md_escape_cell(call.name)}`({_md_escape_cell(_fmt_tool_arguments(call.arguments))})"
        for call in calls
    ]


def _md_response_detail(side: str, model, text: str, tool_calls) -> List[str]:
    """A collapsible block for one response side: prose, then any tool calls.

    Tool calls render as their own list rather than inlined into the prose, so
    a tool-calling step reads as *what the model decided to do* — and an
    empty-text tool call doesn't look like an empty response.
    """
    out = [f"<details><summary>{side} ({model or '?'})</summary>", ""]
    if text or not tool_calls:
        out += [_md_fence(text), ""]
    if tool_calls:
        out += ["**Tool calls:**", "", *_md_tool_calls(tool_calls), ""]
    out += ["</details>"]
    return out


def render_markdown(
    report: MigrationReport,
    *,
    pricing: PricingArg = None,
    max_detail_rows: int = DEFAULT_MAX_DETAIL_ROWS,
) -> str:
    lines: List[str] = []
    baselines = ", ".join(report.baseline_models) or "unknown"
    breakdown = report.by_category()
    pricings = _pricing_list(pricing)
    category_rows = _rows_by_category(report) if (pricings and breakdown) else {}
    lines.append(f"# Migration Report — {baselines} → {report.target_model}")
    lines.append("")

    # One consolidated Summary: a metadata line, the comparator verdict table,
    # and a baseline→target totals table — replacing the old header bullets,
    # the verdict blockquote and a separate summary table that all overlapped.
    lines.append(
        f"`{report.corpus or '<memory>'}` · target `{report.target_model}` "
        f"({report.target_provider}) · generated {report.generated_at} · "
        f"comparators {', '.join(report.comparator_names)}"
    )
    lines.append("")
    lines.append(
        f"**{len(report.ok_rows)} compared** "
        f"({report.cached_count} cached, {report.live_count} live) · "
        f"{len(report.skipped_rows)} skipped · {len(report.error_rows)} errored"
    )
    lines.append("")

    for warning in report.warnings:
        lines.append(f"**⚠ Warning:** {warning}")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.extend(_md_table(_summary_table(report)))
    lines.append("")

    totals, has_latency = _totals_table(report, pricings)
    if totals:
        lines.extend(_md_table(totals))
        lines.append("")
        if has_latency:
            lines.append(f"_{_LATENCY_CAVEAT}_")
            lines.append("")

    if report.gates():
        lines.append("## Strict gate")
        lines.append("")
        lines.append(
            "_Comparators named in `--min-pass` gate the run; the others are informational._"
        )
        lines.append("")
        lines.extend(_md_table(_gate_table(report)))
        lines.append("")

    if breakdown:
        lines.append("## By category")
        lines.append("")
        lines.append(
            "_Cells are pass rate · mean score. Out tokens and Latency are "
            "target/baseline ratios._"
        )
        lines.append("")
        lines.extend(_md_table(_category_table(report, breakdown, pricings, category_rows)))
        lines.append("")

    if report.ok_rows:
        lines.append("## Results")
        lines.append("")
        lines.extend(_md_table(_results_table(report, breakdown, pricings)))
        lines.append("")

        ordered = _ordered_detail_rows(report.ok_rows)
        shown = ordered if max_detail_rows <= 0 else ordered[:max_detail_rows]
        omitted = len(ordered) - len(shown)
        lines.append("## Details")
        lines.append("")
        lines.append("_Failing rows first, then lowest mean score._")
        lines.append("")
        for index, row in shown:
            marker = "🔧 " if _has_tool_calls(row) else ""
            lines.append(f"### {index}. {marker}{row.prompt_preview}")
            lines.append("")
            meta = (
                f"`{row.baseline_id}` → `{row.migration_id}` · semantic key `{row.semantic_key}`"
            )
            if row.category:
                meta += f" · category `{row.category}`"
            if row.baseline_out_tokens is not None or row.target_out_tokens is not None:
                meta += f" · out tokens {_fmt_out_tokens(row)}"
            if row.baseline_latency_s is not None or row.target_latency_s is not None:
                meta += f" · latency {_fmt_latency(row)}"
            if (
                row.baseline_latency_first_chunk_s is not None
                or row.target_latency_first_chunk_s is not None
            ):
                meta += f" · TTFB {_fmt_first_chunk(row)}"
            lines.append(meta)
            for note in row.notes:
                lines.append(f"- _{note}_")
            lines.append("")
            for comparison in row.comparisons:
                mark = "⚠️" if comparison.error else {True: "✅", False: "❌", None: "•"}[comparison.passed]
                lines.append(
                    f"- **{comparison.comparator}** {mark} {comparison.score:.2f} — {comparison.detail}"
                )
            lines.append("")
            lines.append("<details><summary>Prompt</summary>")
            lines.append("")
            lines.append(_md_fence(row.prompt_text))
            lines.append("")
            lines.append("</details>")
            lines.extend(
                _md_response_detail("Baseline", row.baseline_model, row.baseline_text,
                                    row.baseline_tool_calls)
            )
            lines.extend(
                _md_response_detail("Target", row.target_model, row.target_text or "",
                                    row.target_tool_calls)
            )
            lines.append("")
        if omitted:
            lines.append(
                f"_… {omitted} more row{'s' if omitted != 1 else ''} omitted; see the "
                "Results table or pass `--max-detail-rows 0`._"
            )
            lines.append("")

    leftovers = report.skipped_rows + report.error_rows
    if leftovers:
        lines.append("## Skipped & errors")
        lines.append("")
        lines.append("| Cassette | Status | Reason |")
        lines.append("|---|---|---|")
        for row in leftovers:
            lines.append(
                f"| `{row.baseline_id}` | {row.status} | {_md_escape_cell(row.reason or '')} |"
            )
        lines.append("")

    if pricings:
        lines.append("## Pricing")
        lines.append("")
        lines.append(
            "_Cost is derived at report time from recorded tokens and the snapshots "
            "below; cassettes store tokens only. `*` marks estimates where some token "
            "categories had no rate in the profile._"
        )
        lines.append("")
        for entry in pricings:
            lines.append(f"- **{entry.profile}** ({entry.currency}, as-of {entry.as_of}):")
            for ref in entry.snapshots:
                lines.append(
                    f"  - snapshot `{ref.snapshot}` (effective {ref.effective}, "
                    f"sha256 `{ref.digest[:12]}…`)"
                )
            if not entry.snapshots:
                lines.append("  - no rates resolved for any model in this report")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML (self-contained, no JS)
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; margin: 2rem auto;
       max-width: 70rem; padding: 0 1rem; color: #1f2328; line-height: 1.5; }
h1 { border-bottom: 2px solid #d0d7de; padding-bottom: .4rem; }
table { border-collapse: collapse; margin: 1rem 0; width: 100%; }
th, td { border: 1px solid #d0d7de; padding: .4rem .7rem; text-align: left; }
th { background: #f6f8fa; }
.verdict { background: #f6f8fa; border-left: 4px solid #0969da; padding: .7rem 1rem;
           margin: 1rem 0; font-weight: 600; }
.pass { background: #e6f4ea; }
.fail { background: #fdecea; }
.err  { background: #fff8e1; }
.meta { color: #59636e; font-size: .9rem; }
.tag  { background: #ddf4ff; color: #0969da; border-radius: 999px; padding: .05rem .55rem;
        font-size: .8rem; white-space: nowrap; }
details { margin: .8rem 0; }
summary { cursor: pointer; font-weight: 600; }
.panes { display: flex; gap: 1rem; flex-wrap: wrap; }
.pane { flex: 1 1 20rem; min-width: 18rem; }
pre { background: #f6f8fa; padding: .8rem; border-radius: 6px; white-space: pre-wrap;
      word-break: break-word; font-size: .85rem; }
code { background: #f6f8fa; padding: .1rem .3rem; border-radius: 4px; font-size: .85rem; }
.note { color: #59636e; font-style: italic; font-size: .9rem; }
"""


def _html_cell_class(row: RowResult, name: str) -> str:
    for comparison in row.comparisons:
        if comparison.comparator == name:
            if comparison.error:
                return "err"
            if comparison.passed is True:
                return "pass"
            if comparison.passed is False:
                return "fail"
    return ""


def _html_response_pane(side: str, model, text: str, tool_calls) -> str:
    """One side of the side-by-side detail panes: prose then a tool-call list."""
    esc = _html.escape
    out = [f"<div class='pane'><p><b>{side} ({esc(model or '?')})</b></p>"]
    if text or not tool_calls:
        out.append(f"<pre>{esc(text)}</pre>")
    if tool_calls:
        out.append("<p><b>Tool calls</b></p><ul>")
        for call in tool_calls:
            out.append(
                f"<li><code>{esc(call.name)}</code>"
                f"(<code>{esc(_fmt_tool_arguments(call.arguments))}</code>)</li>"
            )
        out.append("</ul>")
    out.append("</div>")
    return "".join(out)


def render_html(
    report: MigrationReport,
    *,
    pricing: PricingArg = None,
    max_detail_rows: int = DEFAULT_MAX_DETAIL_ROWS,
) -> str:
    esc = _html.escape
    baselines = ", ".join(report.baseline_models) or "unknown"
    breakdown = report.by_category()
    pricings = _pricing_list(pricing)
    category_rows = _rows_by_category(report) if (pricings and breakdown) else {}
    parts: List[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append(f"<title>Migration Report — {esc(report.target_model)}</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")
    parts.append(f"<h1>Migration Report — {esc(baselines)} → {esc(report.target_model)}</h1>")
    parts.append(
        "<p class='meta'>"
        f"Corpus <code>{esc(report.corpus or '<memory>')}</code> · "
        f"target <code>{esc(report.target_model)}</code> ({esc(report.target_provider)}) · "
        f"generated {esc(report.generated_at)} · "
        f"comparators: {esc(', '.join(report.comparator_names))}<br>"
        f"<b>{len(report.ok_rows)} compared</b> ({report.cached_count} cached, "
        f"{report.live_count} live) · {len(report.skipped_rows)} skipped · "
        f"{len(report.error_rows)} errored</p>"
    )

    for warning in report.warnings:
        parts.append(f"<p class='note'><b>⚠ Warning:</b> {esc(warning)}</p>")

    # One consolidated Summary: the comparator verdict table plus a
    # baseline→target totals table (tokens / latency / cost).
    parts.append("<h2>Summary</h2>")
    parts.append(_html_table(_summary_table(report)))

    totals, has_latency = _totals_table(report, pricings)
    if totals:
        parts.append(_html_table(totals))
        if has_latency:
            parts.append(f"<p class='note'>{esc(_LATENCY_CAVEAT)}</p>")

    if report.gates():
        parts.append("<h2>Strict gate</h2>")
        parts.append(
            "<p class='meta'>Comparators named in <code>--min-pass</code> gate the run; "
            "the others are informational.</p>"
        )
        parts.append(_html_table(_gate_table(report)))

    if breakdown:
        parts.append("<h2>By category</h2>")
        parts.append(
            "<p class='meta'>Cells are pass rate · mean score. "
            "Out tokens and Latency are target/baseline ratios.</p>"
        )
        parts.append(_html_table(_category_table(report, breakdown, pricings, category_rows)))

    if report.ok_rows:
        parts.append("<h2>Results</h2>")
        parts.append(_html_table(_results_table(report, breakdown, pricings)))

        ordered = _ordered_detail_rows(report.ok_rows)
        shown = ordered if max_detail_rows <= 0 else ordered[:max_detail_rows]
        omitted = len(ordered) - len(shown)
        parts.append("<h2>Details</h2>")
        parts.append("<p class='note'>Failing rows first, then lowest mean score.</p>")
        for index, row in shown:
            marker = "🔧 " if _has_tool_calls(row) else ""
            parts.append(
                f"<details><summary>{marker}{index}. {esc(row.prompt_preview)}</summary>"
            )
            meta = (
                f"<p class='meta'><code>{esc(row.baseline_id)}</code> → "
                f"<code>{esc(row.migration_id)}</code> · semantic key "
                f"<code>{esc(row.semantic_key)}</code>"
            )
            if row.category:
                meta += f" · <span class='tag'>{esc(row.category)}</span>"
            if row.baseline_out_tokens is not None or row.target_out_tokens is not None:
                meta += f" · out tokens {esc(_fmt_out_tokens(row))}"
            if row.baseline_latency_s is not None or row.target_latency_s is not None:
                meta += f" · latency {esc(_fmt_latency(row))}"
            if (
                row.baseline_latency_first_chunk_s is not None
                or row.target_latency_first_chunk_s is not None
            ):
                meta += f" · TTFB {esc(_fmt_first_chunk(row))}"
            parts.append(meta + "</p>")
            for note in row.notes:
                parts.append(f"<p class='note'>{esc(note)}</p>")
            parts.append("<ul>")
            for comparison in row.comparisons:
                parts.append(
                    f"<li><b>{esc(comparison.comparator)}</b> {comparison.score:.2f}"
                    f" — {esc(comparison.detail)}</li>"
                )
            parts.append("</ul>")
            parts.append(f"<p><b>Prompt</b></p><pre>{esc(row.prompt_text)}</pre>")
            parts.append("<div class='panes'>")
            parts.append(_html_response_pane(
                "Baseline", row.baseline_model, row.baseline_text, row.baseline_tool_calls))
            parts.append(_html_response_pane(
                "Target", row.target_model, row.target_text or "", row.target_tool_calls))
            parts.append("</div></details>")
        if omitted:
            parts.append(
                f"<p class='note'>… {omitted} more "
                f"row{'s' if omitted != 1 else ''} omitted; see the Results table "
                "or pass <code>--max-detail-rows 0</code>.</p>"
            )

    leftovers = report.skipped_rows + report.error_rows
    if leftovers:
        parts.append("<h2>Skipped &amp; errors</h2><table>"
                     "<tr><th>Cassette</th><th>Status</th><th>Reason</th></tr>")
        for row in leftovers:
            parts.append(
                f"<tr><td><code>{esc(row.baseline_id)}</code></td>"
                f"<td>{esc(row.status)}</td><td>{esc(row.reason or '')}</td></tr>"
            )
        parts.append("</table>")

    if pricings:
        parts.append("<h2>Pricing</h2>")
        parts.append(
            "<p class='meta'>Cost is derived at report time from recorded tokens and "
            "the snapshots below; cassettes store tokens only. * marks estimates where "
            "some token categories had no rate in the profile.</p><ul>"
        )
        for entry in pricings:
            snapshots = (
                "; ".join(
                    f"<code>{esc(ref.snapshot)}</code> (effective {esc(ref.effective)}, "
                    f"sha256 <code>{esc(ref.digest[:12])}…</code>)"
                    for ref in entry.snapshots
                )
                or "no rates resolved for any model in this report"
            )
            parts.append(
                f"<li><b>{esc(entry.profile)}</b> ({esc(entry.currency)}, "
                f"as-of {esc(entry.as_of)}): {snapshots}</li>"
            )
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Console (ASCII-safe for Windows terminals)
# ---------------------------------------------------------------------------


def render_console(report: MigrationReport, *, pricing: PricingArg = None) -> str:
    lines = [
        f"Migration report: {len(report.ok_rows)} prompts -> {report.target_model} "
        f"({report.cached_count} cached, {report.live_count} live, "
        f"{len(report.skipped_rows)} skipped, {len(report.error_rows)} errors)"
    ]
    for warning in report.warnings:  # ASCII-safe (console runs on Windows too)
        lines.append(f"  ! warning: {warning}")
    for agg in report.aggregates():
        passed = (
            "n/a"
            if agg.pass_rate is None
            else f"{agg.passed}/{agg.passed + agg.failed} passed ({agg.pass_rate:.0%})"
        )
        mean = "n/a" if agg.mean_score is None else f"{agg.mean_score:.2f}"
        lines.append(f"  {agg.comparator:<10} {passed:<22} mean {mean}")
    gates = report.gates()
    if gates:
        for gate in gates:
            status = "PASS" if gate.passed else "FAIL"
            lines.append(f"  gate {gate.comparator}: {gate.detail} -> {status}")
        lines.append(
            "  strict gate: " + ("PASS" if report.strict_passed else "FAIL")
            + " (ungated comparators are informational)"
        )
    totals = report.token_totals()
    if totals and totals.ratio is not None:
        lines.append(
            f"  out tokens baseline {totals.baseline_out:,} -> "
            f"target {totals.target_out:,} ({totals.ratio:.2f}x)"
        )
    latency = report.latency_stats()
    if latency and latency.ratio is not None:
        lines.append(
            f"  latency baseline mean {latency.baseline_mean_s:.2f}s -> "
            f"target mean {latency.target_mean_s:.2f}s ({latency.ratio:.2f}x; "
            "baseline is recording-time provenance)"
        )
        if latency.first_chunk_ratio is not None:
            lines.append(
                f"  TTFB baseline mean {latency.baseline_first_chunk_mean_s:.2f}s -> "
                f"target mean {latency.target_first_chunk_mean_s:.2f}s "
                f"({latency.first_chunk_ratio:.2f}x; both sides streamed)"
            )
    for entry in _pricing_list(pricing):
        lines.append("  " + _pricing_summary(entry, report, arrow="->", times="x"))
    for row in report.skipped_rows + report.error_rows:
        lines.append(f"  [{row.status}] {row.baseline_id}: {row.reason}")
    return "\n".join(lines)
