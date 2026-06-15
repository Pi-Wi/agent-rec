"""
Command-line interface: ``python -m agentrec <command>`` (or ``agentrec ...``).

migrate   Run the corpus against a target model (records new responses into
          the corpus) and write a Markdown/HTML migration report.
report    Re-render the report fully offline from already-recorded cassettes;
          the offline comparators (exact, fuzzy, json, toolcalls) are
          allowed, plus judge served from corpus-cached verdicts.
annotate  Backfill human-readable summary blocks and fingerprint metadata
          into existing cassettes.
import     Turn an observability export (Langfuse / LangSmith / OpenTelemetry
          GenAI spans) into synthesized cassettes the runner can migrate.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .comparators import OFFLINE_COMPARATOR_NAMES, build_comparators, parse_compare_spec
from .importers import SOURCES, import_corpus
from .migration import annotate_corpus, run_migration
# PricingError subclasses ValueError, so a bad snapshot/--pricing-as-of value
# lands in main()'s existing usage-error handler (exit 2).
from .pricing import PricingCatalog, ReportPricing, price_report
from .report import default_report_basename, render_console, render_html, render_markdown
from .store import FileStore


def _add_report_args(parser: argparse.ArgumentParser, *, default_compare: str) -> None:
    parser.add_argument("--corpus", default="corpus", help="corpus directory (default: corpus)")
    parser.add_argument("--target", required=True, help="target model id, e.g. claude-haiku-4-5")
    parser.add_argument(
        "--compare",
        default=default_compare,
        help=f"comma-separated comparators or 'all' (default: {default_compare})",
    )
    parser.add_argument(
        "--target-provider",
        default=None,
        help="override the provider inferred from the target model id",
    )
    parser.add_argument("--judge-model", default="claude-opus-4-8", help="model for the judge comparator")
    parser.add_argument(
        "--embedding-model", default="text-embedding-3-small", help="model for the embedding comparator"
    )
    parser.add_argument("--fuzzy-threshold", type=float, default=0.8)
    parser.add_argument("--embedding-threshold", type=float, default=0.8)
    parser.add_argument(
        "--max-tokens", type=int, default=4096,
        help="max_tokens for target requests when the baseline did not set one",
    )
    parser.add_argument("--filter", default=None, help="only baselines whose id contains this substring")
    parser.add_argument(
        "--concurrency", type=int, default=8,
        help="rows scored in parallel (default: 8)",
    )
    parser.add_argument(
        "--format", choices=("md", "html", "both"), default="both", help="report format(s) to write"
    )
    parser.add_argument(
        "--out", default=None,
        help="explicit output base path (extension added per format); overrides "
             "--out-dir. Default base name: migration-report__<target>__<timestamp>",
    )
    parser.add_argument(
        "--out-dir", default="reports", metavar="DIR",
        help="directory the report files are written to when --out is not given "
             "(default: reports; created if missing)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="exit with code 1 if the run failed the gate: any failed/errored "
             "comparison, or — with --min-pass — any comparator below its threshold",
    )
    parser.add_argument(
        "--min-pass", action="append", default=[], metavar="COMPARATOR=RATE",
        help="gate --strict on a comparator's pass rate instead of every row "
             '(repeatable, e.g. --min-pass json=1.0 --min-pass "json:category,priority"=0.9); '
             "comparators without a threshold become informational",
    )
    parser.add_argument(
        "--pricing", action="append", default=[], metavar="PROFILE",
        help="add estimated-cost columns priced under this profile "
             "(repeatable/comma-separated; 'a+b' composes profiles, e.g. "
             "'anthropic-list+openai-list' for cross-provider migrations)",
    )
    parser.add_argument(
        "--pricing-dir", action="append", default=[], metavar="DIR",
        help="directory of pricing snapshots merged over the built-in profiles "
             "(repeatable; a profile with a built-in's name replaces it)",
    )
    parser.add_argument(
        "--pricing-as-of", default="latest", metavar="WHEN",
        help="snapshot date policy: 'latest' (default), 'recorded' "
             "(each row at its cassette's recorded_at), or a YYYY-MM-DD date",
    )


def _parse(argv: Optional[List[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agentrec", description="Record/replay LLM corpus tooling and migration reports."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser(
        "migrate", help="run corpus prompts against a target model and write a migration report"
    )
    _add_report_args(migrate, default_compare="exact,fuzzy")

    report = sub.add_parser(
        "report", help="re-render a migration report offline from recorded cassettes"
    )
    _add_report_args(report, default_compare="exact,fuzzy")

    annotate = sub.add_parser(
        "annotate", help="backfill summary blocks and metadata into existing cassettes"
    )
    annotate.add_argument("--corpus", default="corpus", help="corpus directory (default: corpus)")

    importer = sub.add_parser(
        "import", help="import an observability export into the corpus as cassettes"
    )
    importer.add_argument("--corpus", default="corpus", help="corpus directory (default: corpus)")
    importer.add_argument(
        "--input", required=True, metavar="FILE",
        help="export file to import (JSON, JSONL, or OTLP spans)",
    )
    importer.add_argument(
        "--source", default="auto", choices=("auto", *SOURCES),
        help="export format (default: auto-detect)",
    )
    importer.add_argument(
        "--category", default=None,
        help="report category to tag every imported row with (when the source carried none)",
    )

    return parser.parse_args(argv)


def _write_reports(args: argparse.Namespace, report, pricing: List[ReportPricing]) -> List[Path]:
    if args.out:
        base = Path(args.out)
        # Strip a user-supplied .md/.html so we can add the per-format extension.
        if base.suffix.lower() in (".md", ".html"):
            base = base.with_name(base.stem)
    else:
        # Default: a dedicated reports directory, not the working directory.
        base = Path(args.out_dir) / default_report_basename(args.target)
    base.parent.mkdir(parents=True, exist_ok=True)
    renderers = []
    if args.format in ("md", "both"):
        renderers.append((".md", render_markdown))
    if args.format in ("html", "both"):
        renderers.append((".html", render_html))
    written: List[Path] = []
    for suffix, render in renderers:
        # Concatenate the extension instead of Path.with_suffix: a target id like
        # gemini-2.5-flash contains a dot that with_suffix would mistake for an
        # extension and truncate the filename.
        path = base.parent / (base.name + suffix)
        path.write_text(render(report, pricing=pricing), encoding="utf-8")
        written.append(path)
    return written


def _price_report(args: argparse.Namespace, report) -> List[ReportPricing]:
    """One ReportPricing per --pricing profile spec (empty without the flag)."""
    specs = [spec.strip() for item in args.pricing for spec in item.split(",") if spec.strip()]
    if not specs:
        return []
    catalog = PricingCatalog.load(*args.pricing_dir)
    return [
        price_report(report, catalog.profile(spec), as_of=args.pricing_as_of)
        for spec in specs
    ]


def _parse_min_pass(items: List[str], comparator_names: List[str]) -> Dict[str, float]:
    """Parse repeated ``--min-pass COMPARATOR=RATE`` flags against the run's
    comparators.  ``rpartition`` on ``=``: comparator names may contain
    ``:`` and ``,`` (``json:category,priority=0.9``)."""
    out: Dict[str, float] = {}
    for item in items:
        name, sep, value = item.rpartition("=")
        if not sep or not name:
            raise ValueError(f"--min-pass expects COMPARATOR=RATE, got {item!r}")
        try:
            rate = float(value)
        except ValueError:
            raise ValueError(f"--min-pass rate must be a number, got {value!r}") from None
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"--min-pass rate must be within 0..1, got {value}")
        if name not in comparator_names:
            raise ValueError(
                f"--min-pass names a comparator not in this run: {name!r} "
                f"(this run has: {', '.join(comparator_names)})"
            )
        out[name] = rate
    return out


async def _run_report_command(args: argparse.Namespace, *, offline: bool) -> int:
    if offline:
        # `all` stays the conservative offline set; an explicit `judge` is
        # allowed because cached verdicts replay without a socket.
        if args.compare.strip().lower() == "all":
            args.compare = ",".join(OFFLINE_COMPARATOR_NAMES)
        parsed = parse_compare_spec(args.compare)
        online = [
            entry.name
            for entry in parsed
            if entry.base not in OFFLINE_COMPARATOR_NAMES and entry.base != "judge"
        ]
        if online:
            print(
                f"report (offline) supports only {', '.join(OFFLINE_COMPARATOR_NAMES)} "
                "(and judge, served from cached verdicts); "
                f"drop: {', '.join(online)} (use `agentrec migrate` for live comparators)",
                file=sys.stderr,
            )
            return 2
        args.compare = ",".join(entry.name for entry in parsed)

    store = FileStore(args.corpus)
    comparators = build_comparators(
        args.compare,
        judge_model=args.judge_model,
        embedding_model=args.embedding_model,
        fuzzy_threshold=args.fuzzy_threshold,
        embedding_threshold=args.embedding_threshold,
        store=store,
        offline=offline,
    )
    min_pass = _parse_min_pass(args.min_pass, [c.name for c in comparators])
    report = await run_migration(
        store,
        args.target,
        comparators,
        target_provider=args.target_provider,
        offline=offline,
        max_tokens_default=args.max_tokens,
        filter_substr=args.filter,
        concurrency=args.concurrency,
        min_pass=min_pass,
    )
    pricing = _price_report(args, report)
    written = _write_reports(args, report, pricing)
    print(render_console(report, pricing=pricing))
    for path in written:
        print(f"Report written: {path}")
    if not report.ok_rows:
        print(
            "warning: no prompts were actually compared (all rows skipped or "
            "errored) — with --strict this counts as a failure",
            file=sys.stderr,
        )
    if args.strict and not report.strict_passed:
        return 1
    return 0


async def _run_annotate(args: argparse.Namespace) -> int:
    annotated = await annotate_corpus(FileStore(args.corpus))
    print(f"Annotated {len(annotated)} cassette(s) in {args.corpus}")
    return 0


async def _run_import(args: argparse.Namespace) -> int:
    summary = await import_corpus(
        args.input, FileStore(args.corpus), source=args.source, category=args.category
    )
    print(
        f"Imported {summary.imported_count} cassette(s) from {summary.source} export "
        f"into {args.corpus} ({summary.skipped_count} skipped)"
    )
    # Surface the first few skip reasons so silent data loss is visible.
    for ref, reason in summary.skipped[:10]:
        print(f"  skipped {ref}: {reason}", file=sys.stderr)
    if summary.skipped_count > 10:
        print(f"  ... and {summary.skipped_count - 10} more", file=sys.stderr)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse(argv)
    try:
        if args.command == "migrate":
            return asyncio.run(_run_report_command(args, offline=False))
        if args.command == "report":
            return asyncio.run(_run_report_command(args, offline=True))
        if args.command == "annotate":
            return asyncio.run(_run_annotate(args))
        if args.command == "import":
            return asyncio.run(_run_import(args))
    except (ValueError, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
