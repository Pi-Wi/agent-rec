"""
Render a :class:`~agentrec.migration.MigrationReport` for humans.

* ``render_markdown`` — verdict line, per-comparator summary table, per-category
  breakdown, per-prompt results table, collapsible full-text details.
* ``render_html``     — self-contained single file (inline CSS, no JS) with
  color-coded scores, the category breakdown and side-by-side panels; the
  primary artifact.
* ``render_console``  — a few ASCII-safe lines for the terminal.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
from typing import List, Optional

from .keying import _sanitize
from .migration import ComparatorAggregate, MigrationReport, RowResult


def default_report_basename(target_model: str, when: Optional[_dt.datetime] = None) -> str:
    when = when or _dt.datetime.now()
    return f"migration-report__{_sanitize(target_model)}__{when.strftime('%Y%m%d-%H%M%S')}"


def _fmt_score(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.2f}"


def _fmt_rate(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.0%}"


def _fmt_ratio(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.2f}×"


def _fmt_out_tokens(row: RowResult) -> str:
    """Per-row output-token cell, e.g. ``12→34`` ('–' when nothing is known)."""
    if row.baseline_out_tokens is None and row.target_out_tokens is None:
        return "–"
    baseline = "?" if row.baseline_out_tokens is None else str(row.baseline_out_tokens)
    target = "?" if row.target_out_tokens is None else str(row.target_out_tokens)
    return f"{baseline}→{target}"


def _verdict(report: MigrationReport) -> str:
    parts = []
    if report.min_pass:
        parts.append(
            "strict gate " + ("PASSED" if report.strict_passed else "FAILED")
        )
    for agg in report.aggregates():
        if agg.compared == 0:
            parts.append(f"{agg.comparator}: no results")
        elif agg.pass_rate is not None:
            parts.append(
                f"{agg.comparator} {agg.passed}/{agg.passed + agg.failed} passed"
                f" · mean {_fmt_score(agg.mean_score)}"
            )
        else:
            parts.append(f"{agg.comparator} mean {_fmt_score(agg.mean_score)}")
    return " · ".join(parts) if parts else "no comparators run"


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


def render_markdown(report: MigrationReport) -> str:
    lines: List[str] = []
    baselines = ", ".join(report.baseline_models) or "unknown"
    breakdown = report.by_category()
    totals = report.token_totals()
    lines.append(f"# Migration Report — {baselines} → {report.target_model}")
    lines.append("")
    lines.append(f"- **Corpus:** `{report.corpus or '<memory>'}`")
    lines.append(f"- **Target:** `{report.target_model}` ({report.target_provider})")
    lines.append(f"- **Generated:** {report.generated_at}")
    lines.append(f"- **Comparators:** {', '.join(report.comparator_names)}")
    lines.append(
        f"- **Prompts:** {len(report.ok_rows)} compared "
        f"({report.cached_count} from corpus cache, {report.live_count} live), "
        f"{len(report.skipped_rows)} skipped, {len(report.error_rows)} errored"
    )
    if totals:
        lines.append(
            f"- **Output tokens:** baseline {totals.baseline_out:,} → "
            f"target {totals.target_out:,} ({_fmt_ratio(totals.ratio)}, "
            f"over {totals.rows} prompts)"
        )
    lines.append("")
    lines.append(f"> **Verdict:** {_verdict(report)}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Comparator | Compared | Passed | Pass rate | Mean score |")
    lines.append("|---|---:|---:|---:|---:|")
    for agg in report.aggregates():
        passed = "–" if agg.pass_rate is None else f"{agg.passed}/{agg.passed + agg.failed}"
        lines.append(
            f"| {agg.comparator} | {agg.compared} | {passed} "
            f"| {_fmt_rate(agg.pass_rate)} | {_fmt_score(agg.mean_score)} |"
        )
    lines.append("")

    gates = report.gates()
    if gates:
        lines.append("## Strict gate")
        lines.append("")
        lines.append(
            "_Comparators named in `--min-pass` gate the run; the others are informational._"
        )
        lines.append("")
        lines.append("| Comparator | Threshold | Pass rate | Errors | Verdict |")
        lines.append("|---|---:|---:|---:|---|")
        for gate in gates:
            mark = "✅ pass" if gate.passed else "❌ fail"
            lines.append(
                f"| {gate.comparator} | {_fmt_rate(gate.threshold)} "
                f"| {_fmt_rate(gate.pass_rate)} | {gate.errors} "
                f"| {mark} — {_md_escape_cell(gate.detail)} |"
            )
        lines.append("")

    if breakdown:
        lines.append("## By category")
        lines.append("")
        lines.append("_Cells are pass rate · mean score. Out tokens is the target/baseline output-token ratio._")
        lines.append("")
        header = ["Category", "Prompts"] + report.comparator_names + ["Out tokens"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|---|---:|" + "---:|" * (len(report.comparator_names) + 1))
        for cat in breakdown:
            cells = [cat.category, str(cat.prompts)]
            cells.extend(_aggregate_cell(agg) for agg in cat.aggregates)
            cells.append(_fmt_ratio(cat.tokens.ratio) if cat.tokens else "–")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    if report.ok_rows:
        lines.append("## Results")
        lines.append("")
        header = ["#", "Prompt"]
        if breakdown:
            header.append("Category")
        header += ["Baseline model"] + report.comparator_names + ["Out tok", "Cached"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for index, row in enumerate(report.ok_rows, 1):
            cells = [str(index), _md_escape_cell(row.prompt_preview)]
            if breakdown:
                cells.append(row.category or "–")
            cells += [
                row.baseline_model or "?",
                *[_comparison_cell(row, name) for name in report.comparator_names],
                _fmt_out_tokens(row),
                "✅" if row.cached else "live",
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

        lines.append("## Details")
        lines.append("")
        for index, row in enumerate(report.ok_rows, 1):
            lines.append(f"### {index}. {row.prompt_preview}")
            lines.append("")
            meta = (
                f"`{row.baseline_id}` → `{row.migration_id}` · semantic key `{row.semantic_key}`"
            )
            if row.category:
                meta += f" · category `{row.category}`"
            if row.baseline_out_tokens is not None or row.target_out_tokens is not None:
                meta += f" · out tokens {_fmt_out_tokens(row)}"
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
            lines.append(f"<details><summary>Baseline ({row.baseline_model})</summary>")
            lines.append("")
            lines.append(_md_fence(row.baseline_text))
            lines.append("")
            lines.append("</details>")
            lines.append(f"<details><summary>Target ({row.target_model})</summary>")
            lines.append("")
            lines.append(_md_fence(row.target_text or ""))
            lines.append("")
            lines.append("</details>")
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


def render_html(report: MigrationReport) -> str:
    esc = _html.escape
    baselines = ", ".join(report.baseline_models) or "unknown"
    breakdown = report.by_category()
    totals = report.token_totals()
    parts: List[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append(f"<title>Migration Report — {esc(report.target_model)}</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")
    parts.append(f"<h1>Migration Report — {esc(baselines)} → {esc(report.target_model)}</h1>")
    meta = (
        "<p class='meta'>"
        f"Corpus <code>{esc(report.corpus or '<memory>')}</code> · "
        f"target <code>{esc(report.target_model)}</code> ({esc(report.target_provider)}) · "
        f"generated {esc(report.generated_at)} · "
        f"comparators: {esc(', '.join(report.comparator_names))}<br>"
        f"{len(report.ok_rows)} prompts compared ({report.cached_count} cached, "
        f"{report.live_count} live), {len(report.skipped_rows)} skipped, "
        f"{len(report.error_rows)} errored"
    )
    if totals:
        meta += (
            f"<br>output tokens: baseline {totals.baseline_out:,} → "
            f"target {totals.target_out:,} ({esc(_fmt_ratio(totals.ratio))} "
            f"over {totals.rows} prompts)"
        )
    parts.append(meta + "</p>")
    parts.append(f"<div class='verdict'>{esc(_verdict(report))}</div>")

    parts.append("<h2>Summary</h2><table><tr><th>Comparator</th><th>Compared</th>"
                 "<th>Passed</th><th>Pass rate</th><th>Mean score</th></tr>")
    for agg in report.aggregates():
        passed = "–" if agg.pass_rate is None else f"{agg.passed}/{agg.passed + agg.failed}"
        parts.append(
            f"<tr><td>{esc(agg.comparator)}</td><td>{agg.compared}</td><td>{passed}</td>"
            f"<td>{_fmt_rate(agg.pass_rate)}</td><td>{_fmt_score(agg.mean_score)}</td></tr>"
        )
    parts.append("</table>")

    gates = report.gates()
    if gates:
        parts.append("<h2>Strict gate</h2>")
        parts.append(
            "<p class='meta'>Comparators named in <code>--min-pass</code> gate the run; "
            "the others are informational.</p>"
        )
        parts.append("<table><tr><th>Comparator</th><th>Threshold</th>"
                     "<th>Pass rate</th><th>Errors</th><th>Verdict</th></tr>")
        for gate in gates:
            cell_class = "pass" if gate.passed else "fail"
            mark = "pass" if gate.passed else "fail"
            parts.append(
                f"<tr><td>{esc(gate.comparator)}</td><td>{_fmt_rate(gate.threshold)}</td>"
                f"<td>{_fmt_rate(gate.pass_rate)}</td><td>{gate.errors}</td>"
                f"<td class='{cell_class}'>{mark} — {esc(gate.detail)}</td></tr>"
            )
        parts.append("</table>")

    if breakdown:
        parts.append("<h2>By category</h2>")
        parts.append(
            "<p class='meta'>Cells are pass rate · mean score. "
            "Out tokens is the target/baseline output-token ratio.</p>"
        )
        parts.append("<table><tr><th>Category</th><th>Prompts</th>")
        for name in report.comparator_names:
            parts.append(f"<th>{esc(name)}</th>")
        parts.append("<th>Out tokens</th></tr>")
        for cat in breakdown:
            parts.append(
                f"<tr><td><span class='tag'>{esc(cat.category)}</span></td>"
                f"<td>{cat.prompts}</td>"
            )
            for agg in cat.aggregates:
                parts.append(f"<td>{esc(_aggregate_cell(agg))}</td>")
            ratio = _fmt_ratio(cat.tokens.ratio) if cat.tokens else "–"
            parts.append(f"<td>{esc(ratio)}</td></tr>")
        parts.append("</table>")

    if report.ok_rows:
        parts.append("<h2>Results</h2><table><tr><th>#</th><th>Prompt</th>")
        if breakdown:
            parts.append("<th>Category</th>")
        parts.append("<th>Baseline</th>")
        for name in report.comparator_names:
            parts.append(f"<th>{esc(name)}</th>")
        parts.append("<th>Out tok</th><th>Cached</th></tr>")
        for index, row in enumerate(report.ok_rows, 1):
            parts.append(f"<tr><td>{index}</td><td>{esc(row.prompt_preview)}</td>")
            if breakdown:
                tag = f"<span class='tag'>{esc(row.category)}</span>" if row.category else "–"
                parts.append(f"<td>{tag}</td>")
            parts.append(f"<td>{esc(row.baseline_model or '?')}</td>")
            for name in report.comparator_names:
                parts.append(
                    f"<td class='{_html_cell_class(row, name)}'>"
                    f"{esc(_comparison_cell(row, name))}</td>"
                )
            parts.append(f"<td>{esc(_fmt_out_tokens(row))}</td>")
            parts.append(f"<td>{'yes' if row.cached else 'live'}</td></tr>")
        parts.append("</table>")

        parts.append("<h2>Details</h2>")
        for index, row in enumerate(report.ok_rows, 1):
            parts.append(f"<details><summary>{index}. {esc(row.prompt_preview)}</summary>")
            meta = (
                f"<p class='meta'><code>{esc(row.baseline_id)}</code> → "
                f"<code>{esc(row.migration_id)}</code> · semantic key "
                f"<code>{esc(row.semantic_key)}</code>"
            )
            if row.category:
                meta += f" · <span class='tag'>{esc(row.category)}</span>"
            if row.baseline_out_tokens is not None or row.target_out_tokens is not None:
                meta += f" · out tokens {esc(_fmt_out_tokens(row))}"
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
            parts.append(
                f"<div class='pane'><p><b>Baseline ({esc(row.baseline_model or '?')})</b></p>"
                f"<pre>{esc(row.baseline_text)}</pre></div>"
            )
            parts.append(
                f"<div class='pane'><p><b>Target ({esc(row.target_model)})</b></p>"
                f"<pre>{esc(row.target_text or '')}</pre></div>"
            )
            parts.append("</div></details>")

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

    parts.append("</body></html>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Console (ASCII-safe for Windows terminals)
# ---------------------------------------------------------------------------


def render_console(report: MigrationReport) -> str:
    lines = [
        f"Migration report: {len(report.ok_rows)} prompts -> {report.target_model} "
        f"({report.cached_count} cached, {report.live_count} live, "
        f"{len(report.skipped_rows)} skipped, {len(report.error_rows)} errors)"
    ]
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
    for row in report.skipped_rows + report.error_rows:
        lines.append(f"  [{row.status}] {row.baseline_id}: {row.reason}")
    return "\n".join(lines)
