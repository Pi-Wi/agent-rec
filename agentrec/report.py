"""
Render a :class:`~agentrec.migration.MigrationReport` for humans.

* ``render_markdown`` — the primary artifact: verdict line, per-comparator
  summary table, per-prompt results table, collapsible full-text details.
* ``render_html``     — self-contained single file (inline CSS, no JS) with
  color-coded scores and side-by-side baseline/target panels.
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


def _verdict(report: MigrationReport) -> str:
    parts = []
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

    if report.ok_rows:
        lines.append("## Results")
        lines.append("")
        header = ["#", "Prompt", "Baseline model"] + report.comparator_names + ["Cached"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for index, row in enumerate(report.ok_rows, 1):
            cells = [
                str(index),
                _md_escape_cell(row.prompt_preview),
                row.baseline_model or "?",
                *[_comparison_cell(row, name) for name in report.comparator_names],
                "✅" if row.cached else "live",
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

        lines.append("## Details")
        lines.append("")
        for index, row in enumerate(report.ok_rows, 1):
            lines.append(f"### {index}. {row.prompt_preview}")
            lines.append("")
            lines.append(
                f"`{row.baseline_id}` → `{row.migration_id}` · semantic key `{row.semantic_key}`"
            )
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
        f"{len(report.ok_rows)} prompts compared ({report.cached_count} cached, "
        f"{report.live_count} live), {len(report.skipped_rows)} skipped, "
        f"{len(report.error_rows)} errored</p>"
    )
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

    if report.ok_rows:
        parts.append("<h2>Results</h2><table><tr><th>#</th><th>Prompt</th><th>Baseline</th>")
        for name in report.comparator_names:
            parts.append(f"<th>{esc(name)}</th>")
        parts.append("<th>Cached</th></tr>")
        for index, row in enumerate(report.ok_rows, 1):
            parts.append(
                f"<tr><td>{index}</td><td>{esc(row.prompt_preview)}</td>"
                f"<td>{esc(row.baseline_model or '?')}</td>"
            )
            for name in report.comparator_names:
                parts.append(
                    f"<td class='{_html_cell_class(row, name)}'>"
                    f"{esc(_comparison_cell(row, name))}</td>"
                )
            parts.append(f"<td>{'yes' if row.cached else 'live'}</td></tr>")
        parts.append("</table>")

        parts.append("<h2>Details</h2>")
        for index, row in enumerate(report.ok_rows, 1):
            parts.append(f"<details><summary>{index}. {esc(row.prompt_preview)}</summary>")
            parts.append(
                f"<p class='meta'><code>{esc(row.baseline_id)}</code> → "
                f"<code>{esc(row.migration_id)}</code> · semantic key "
                f"<code>{esc(row.semantic_key)}</code></p>"
            )
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
    for row in report.skipped_rows + report.error_rows:
        lines.append(f"  [{row.status}] {row.baseline_id}: {row.reason}")
    return "\n".join(lines)
