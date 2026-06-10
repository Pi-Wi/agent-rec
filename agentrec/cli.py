"""
Command-line interface: ``python -m agentrec <command>`` (or ``agentrec ...``).

migrate   Run the corpus against a target model (records new responses into
          the corpus) and write a Markdown/HTML migration report.
report    Re-render the report fully offline from already-recorded cassettes;
          only the offline comparators (exact, fuzzy) are allowed.
annotate  Backfill human-readable summary blocks and fingerprint metadata
          into existing cassettes.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

from .comparators import OFFLINE_COMPARATOR_NAMES, build_comparators
from .migration import annotate_corpus, run_migration
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
        "--format", choices=("md", "html", "both"), default="both", help="report format(s) to write"
    )
    parser.add_argument(
        "--out", default=None,
        help="output base path (extension added per format; default: migration-report__<target>__<timestamp>)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="exit with code 1 if any comparison failed or errored (CI gate)",
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

    return parser.parse_args(argv)


def _write_reports(args: argparse.Namespace, report) -> List[Path]:
    base = args.out or default_report_basename(args.target)
    base_path = Path(base)
    if base_path.suffix.lower() in (".md", ".html"):
        base_path = base_path.with_suffix("")
    written: List[Path] = []
    if args.format in ("md", "both"):
        path = base_path.with_suffix(".md")
        path.write_text(render_markdown(report), encoding="utf-8")
        written.append(path)
    if args.format in ("html", "both"):
        path = base_path.with_suffix(".html")
        path.write_text(render_html(report), encoding="utf-8")
        written.append(path)
    return written


async def _run_report_command(args: argparse.Namespace, *, offline: bool) -> int:
    if offline:
        requested = (
            list(OFFLINE_COMPARATOR_NAMES)
            if args.compare.strip().lower() == "all"
            else [name.strip() for name in args.compare.split(",") if name.strip()]
        )
        online = [name for name in requested if name not in OFFLINE_COMPARATOR_NAMES]
        if online:
            print(
                f"report (offline) supports only {', '.join(OFFLINE_COMPARATOR_NAMES)}; "
                f"drop: {', '.join(online)} (use `agentrec migrate` for live comparators)",
                file=sys.stderr,
            )
            return 2
        args.compare = ",".join(requested)

    comparators = build_comparators(
        args.compare,
        judge_model=args.judge_model,
        embedding_model=args.embedding_model,
        fuzzy_threshold=args.fuzzy_threshold,
        embedding_threshold=args.embedding_threshold,
    )
    store = FileStore(args.corpus)
    report = await run_migration(
        store,
        args.target,
        comparators,
        target_provider=args.target_provider,
        offline=offline,
        max_tokens_default=args.max_tokens,
        filter_substr=args.filter,
    )
    written = _write_reports(args, report)
    print(render_console(report))
    for path in written:
        print(f"Report written: {path}")
    if args.strict and not report.all_passed:
        return 1
    return 0


async def _run_annotate(args: argparse.Namespace) -> int:
    annotated = await annotate_corpus(FileStore(args.corpus))
    print(f"Annotated {len(annotated)} cassette(s) in {args.corpus}")
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
    except (ValueError, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
