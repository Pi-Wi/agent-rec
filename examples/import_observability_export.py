"""
Bring a production observability export into agentrec and migrate it — the
**no-recorder** path, and the only example that never touches an LLM SDK.

The other examples record traffic through agentrec's httpx seam. This one covers
the case the README leads with for teams already on an observability backend:
*you have months of Langfuse / LangSmith / OpenTelemetry traces and don't want
to touch prod for a one-off "will the new model hold up?" question.* ``agentrec
import`` reads what you already have and synthesizes cassettes the migration
runner consumes like recorded ones — no OpenAI/Anthropic SDK, and (for the
import + inspect steps below) no API keys and no network at all.

What it does
------------
1. Writes a realistic — and deliberately *messy* — Langfuse generations export
   to ``corpus-imported-src/``. Real exports are not clean: alongside ordinary
   text and tool-calling generations sit non-LLM spans, empty inputs,
   system-only prompts, an image-only turn, PII in a prompt, a provider whose
   SDK you never recorded, missing token counts, odd timestamp encodings, and a
   stray non-JSON line. This is the abuse: can the importer keep the good rows
   and skip the rest *with a reason*, never crashing the run?
2. Imports it into a **hardened** ``FileStore`` and prints exactly what landed
   and what was skipped (with the reason for each skip).
3. Inspects the synthesized cassettes — the OpenAI-dialect shape, the
   ``imported``/``imported_from`` provenance, the cross-provider ``semantic_key``
   — and verifies on disk that secrets/PII were scrubbed.
4. Runs an **offline** migration pass to surface a sharp edge new users hit: a
   freshly imported corpus has baseline answers but no *target* answers yet, so
   ``agentrec report`` (offline) skips every row until you ``migrate`` once.
5. With ``--migrate`` (and the target provider's key), re-asks every imported
   prompt of the target, scores it, prices it, and writes the report.

Two DevEx notes this example is built to demonstrate
----------------------------------------------------
* **The CLI ``agentrec import`` can't harden PII.** It constructs a default
  ``FileStore``, which scrubs known *credential* shapes (an ``sk-…`` key) but
  not PII like emails or national-id numbers, and never scrubs response bodies.
  For production traffic, import from Python (as here) with
  ``scrub_response_body=True`` and your own ``secret_patterns=[...]`` — the knobs
  the CLI doesn't expose. The run below proves both: the default would leak the
  email; the hardened store does not.
* **Image-only turns are skipped honestly.** Non-text content (images) is
  dropped; a turn that was *only* an image has no text left to ask, so the
  importer skips it with a reason instead of synthesizing an empty prompt that
  would 400 the target and error the migration row. The generated export
  includes one such turn — watch it land in the skip list, not the corpus.
  (This is a guardrail, not vision support: real multimodal migration is still
  an honest skip — see ``TODO.md``.)

Run from the project root (import + inspect + offline preview need no keys)::

    .venv\\Scripts\\python.exe examples\\import_observability_export.py

Add ``--migrate`` to re-ask the target live (needs the target provider's key in
the repo-root ``.env`` — ``ANTHROPIC_API_KEY`` for the default Claude target)::

    .venv\\Scripts\\python.exe examples\\import_observability_export.py --migrate

Flags::

    --input FILE       import this export instead of the generated one
    --source SRC       langfuse|langsmith|otel|auto (default: auto-detect)
    --target MODEL     migration target (default: claude-haiku-4-5)
    --compare SPEC     comparators for --migrate (default: exact,fuzzy)
    --migrate          actually re-ask the target (live; costs money)
    --pricing PROFILE  cost columns, e.g. "anthropic-list+openai-list"
    --strict           exit 1 if the migrated run doesn't pass the gate
    --format FMT       report format: html (default), md, or all
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Allow `python examples/import_observability_export.py` from the repo root
# without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentrec import FileStore, build_comparators, import_corpus  # noqa: E402
from agentrec.migration import MIGRATION_PREFIX, RowResult, run_migration  # noqa: E402
from agentrec.report import (  # noqa: E402
    default_report_basename,
    render_console,
    render_html,
    render_markdown,
)
from agentrec.store import DEFAULT_SECRET_PATTERNS  # noqa: E402

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "corpus-imported-src"          # the raw export we synthesize
CORPUS_DIR = ROOT / "corpus-imported"           # the cassettes import writes
EXPORT_PATH = SRC_DIR / "langfuse_export.jsonl"

# Which env var the obvious targets need, so we can give a useful heads-up
# instead of a wall of "skipped: missing API key" rows. Not exhaustive — an
# unlisted target just attempts and reports honestly per row.
TARGET_KEY_HINT = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def _safe_print(text: str) -> None:
    """Print without crashing on a non-cp1252 console (Windows default)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(text.encode(enc, "replace").decode(enc, "replace"))


def _baseline_count(store: FileStore) -> int:
    """Imported/recorded prompts only — exclude the runner's migration cassettes,
    which land in the same store once you've migrated (so counts stay honest on
    a re-run)."""
    return sum(1 for i in store.ids() if not i.startswith(MIGRATION_PREFIX))


def build_langfuse_export() -> list:
    """A Langfuse generations export (one object per line), warts and all.

    Each dict mimics a Langfuse ``GENERATION`` observation. The list mixes
    clean production shapes with the edge cases a real export actually contains,
    so the import step has something to skip — and something to mishandle.
    """
    return [
        # --- ordinary production traffic (should import cleanly) -------------
        {
            "id": "gen-classify-1", "type": "GENERATION", "model": "gpt-4o",
            "input": {"messages": [
                {"role": "system", "content": "You are a precise classifier. One word."},
                {"role": "user", "content": "Sentiment (positive/negative/neutral): 'Shipping was fast but it broke in a week.'"},
            ]},
            "output": {"role": "assistant", "content": "negative"},
            "usage": {"input": 28, "output": 1},
            "metadata": {"category": "classify"},
            "startTime": "2026-05-12T09:14:00Z",
        },
        {
            # input as a bare string; model under `modelName`; epoch-ms timestamp.
            "id": "gen-extract-1", "type": "GENERATION", "modelName": "gpt-4o",
            "input": "Extract as JSON {amount, currency}: 'Your total comes to $1,249.99 incl. tax.'",
            "output": "{\"amount\": 1249.99, \"currency\": \"USD\"}",
            "usage": {"promptTokens": 31, "completionTokens": 14},
            "metadata": {"category": "extract"},
            "startTime": 1747041240000,
        },
        {
            # multi-turn conversation — every prior turn rides along.
            "id": "gen-route-1", "type": "GENERATION", "model": "gpt-4o",
            "input": {"messages": [
                {"role": "user", "content": "I was charged twice this month."},
                {"role": "assistant", "content": "I can help with that. Is this on your latest invoice?"},
                {"role": "user", "content": "Yes, two identical charges on the 3rd."},
            ]},
            "output": "This is a billing issue; routing you to our billing team.",
            "usage": {"input": 54, "output": 12},
            "metadata": {"category": "route"},
        },
        {
            # tool call with arguments as an object (Langfuse stores either shape).
            "id": "gen-tool-weather", "type": "GENERATION", "model": "gpt-4o",
            "input": {"messages": [{"role": "user", "content": "What's the weather in Oslo right now?"}]},
            "output": {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "get_weather", "arguments": {"city": "Oslo", "unit": "celsius"}}},
            ]},
            "metadata": {"category": "tool"},
        },
        {
            # tool call with arguments as a JSON *string* (the other common shape).
            "id": "gen-tool-order", "type": "GENERATION", "model": "gpt-4o",
            "input": {"messages": [{"role": "user", "content": "Where is my order #A1043?"}]},
            "output": {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_2", "type": "function",
                 "function": {"name": "look_up_order", "arguments": "{\"order_id\": \"A1043\"}"}},
            ]},
            "metadata": {"category": "tool"},
        },
        {
            # provider you never recorded (its SDK bypasses httpx). Imports as the
            # uniform OpenAI dialect; the real model id is preserved so the report
            # still names who answered, and semantic_key groups it cross-provider.
            "id": "gen-summarize-claude", "type": "GENERATION",
            "model": "claude-3-5-sonnet-20241022", "provider": "anthropic",
            "input": {"messages": [{"role": "user", "content":
                "Summarize in one sentence: the night batch failed twice, was rerun, and db-3 hit 85% disk."}]},
            "output": "Two failed night-batch jobs were rerun successfully while db-3 disk use reached 85%.",
            "usage": {"input": 41, "output": 19},
            "metadata": {"category": "summarize"},
        },
        {
            # unicode / emoji round-trip.
            "id": "gen-translate-ja", "type": "GENERATION", "model": "gpt-4o",
            "input": {"messages": [{"role": "user", "content": "Translate to Japanese: 'good morning' \U0001f305"}]},
            "output": "おはようございます",
            "usage": {"input": 17, "output": 8},
            "metadata": {"category": "translate"},
        },
        {
            # NO usage reported — pricing must flag a missing rate, never bill $0.
            "id": "gen-rewrite-nousage", "type": "GENERATION", "model": "gpt-4o",
            "input": {"messages": [{"role": "user", "content": "Make this polite: 'Send me the report now.'"}]},
            "output": "Could you please send me the report when you have a moment? Thank you.",
            "metadata": {"category": "rewrite"},
        },
        {
            # PII + a real-looking secret in the prompt. The hardened store must
            # scrub all three before anything hits disk.
            "id": "gen-pii", "type": "GENERATION", "model": "gpt-4o",
            "input": {"messages": [{"role": "user", "content":
                "Update my profile. API key sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDwxyz, "
                "email jane.doe@example.com, phone +1 (415) 555-0132, SSN 523-12-9876."}]},
            "output": "Your profile has been updated.",
            "usage": {"input": 45, "output": 6},
            "metadata": {"category": "pii"},
        },

        # --- edge cases the importer should *skip*, each with a reason --------
        # A non-LLM span (retriever/tool/chain) — exports are full of these.
        {"id": "span-retriever", "type": "SPAN", "name": "vector-search",
         "input": {"query": "refund policy"}, "output": {"hits": 5}},
        # Empty input.
        {"id": "gen-empty", "type": "GENERATION", "model": "gpt-4o", "input": {}, "output": "?"},
        # Only a system prompt, no actual user turn.
        {"id": "gen-system-only", "type": "GENERATION", "model": "gpt-4o",
         "input": {"messages": [{"role": "system", "content": "You are helpful."}]}, "output": "ok"},
        # A stray non-JSON-object line (a log line that leaked into the export).
        "2026-05-12T09:20:00Z INFO export job finished, 14 rows",

        # --- the silent gotcha: image-only turn -> empty prompt, NOT a skip --
        {"id": "gen-image-only", "type": "GENERATION", "model": "gpt-4o",
         "input": {"messages": [{"role": "user", "content": [
             {"type": "image_url", "image_url": {"url": "https://cdn.example.com/receipt.png"}}]}]},
         "output": "Total on the receipt is $42.50.",
         "metadata": {"category": "vision"}},
    ]


def write_export() -> int:
    """Write the generated export as JSONL; return the record count."""
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    records = build_langfuse_export()
    EXPORT_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    return len(records)


def hardened_store() -> FileStore:
    """A FileStore configured for *production* traffic.

    The defaults scrub known credential shapes from request bodies only. For
    imported observability data — which is full of user PII and may echo secrets
    in the *response* — we extend the patterns (email / US SSN / phone) and turn
    on response scrubbing. These are exactly the knobs ``agentrec import`` (CLI)
    does not expose, which is why importing production traffic belongs in code.
    """
    extra = [
        (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED-EMAIL]"),
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
        (re.compile(r"\+?\d[\d\s().-]{8,}\d"), "[REDACTED-PHONE]"),
    ]
    return FileStore(
        CORPUS_DIR,
        scrub_response_body=True,
        secret_patterns=DEFAULT_SECRET_PATTERNS + extra,
    )


async def inspect_corpus(store: FileStore) -> None:
    """Show the synthesized shape, provenance, and that PII was scrubbed on disk."""
    baseline_ids = [i for i in store.ids() if not i.startswith(MIGRATION_PREFIX)]

    # One imported cassette, decoded, to show the synthesized OpenAI dialect and
    # the provenance metadata the report relies on.
    sample_id = next((i for i in baseline_ids if i.endswith("gen-summarize-claude")), baseline_ids[0])
    sample = await store.load(sample_id)
    meta = sample.metadata
    _safe_print("\n== a synthesized cassette ==")
    _safe_print(f"  id            : {sample_id}")
    _safe_print(f"  imported_from : {meta.get('imported_from')}  (synthesized: {meta.get('imported')})")
    _safe_print(f"  model on body : {meta.get('model')}   imported_provider: {meta.get('imported_provider')}")
    _safe_print(f"  semantic_key  : {meta.get('semantic_key')}   category: {meta.get('category')}")
    _safe_print(f"  recorded_at   : {meta.get('recorded_at')}")

    # On-disk scrubbing check: the hardened store must leave no PII in the file.
    pii_path = next((p for p in CORPUS_DIR.glob("*gen-pii*")), None)
    if pii_path:
        raw = pii_path.read_text(encoding="utf-8")
        leaks = [s for s in ("sk-ABCDEFGH", "jane.doe@example.com", "523-12-9876", "555-0132") if s in raw]
        _safe_print("\n== PII scrub check (hardened store) ==")
        _safe_print(f"  {pii_path.name}: " + ("LEAKED " + ", ".join(leaks) if leaks else "clean (key, email, phone, SSN all redacted)"))


async def offline_preview(store: FileStore, target: str) -> None:
    """Show the 'imported but not yet migrated' trap, offline and key-free."""
    _safe_print("\n== offline preview: `agentrec report` before any migration ==")
    comparators = build_comparators("exact,fuzzy")
    report = await run_migration(store, target, comparators, offline=True)
    skipped = sum(1 for r in report.rows if r.status == "skipped")
    _safe_print(f"  {len(report.rows)} rows, {skipped} skipped, strict_passed={report.strict_passed}")
    if report.rows:
        _safe_print(f"  reason: {report.rows[0].reason}")
    _safe_print(
        "  -> an imported corpus has baseline answers but no TARGET answers yet,\n"
        "     so the offline report skips every row. Run a live migration once\n"
        "     (`--migrate`, or `agentrec migrate`) to fill them in; re-runs are offline."
    )


async def migrate(store: FileStore, args: argparse.Namespace) -> int:
    """The live payoff: re-ask the target, score, price, render, gate."""
    import httpx  # only --migrate needs the network; import is SDK-free

    provider = args.target_provider or _guess_provider(args.target)
    key_var = TARGET_KEY_HINT.get(provider)
    if key_var and not os.environ.get(key_var):
        _safe_print(
            f"\n[warn] {key_var} not set — every row will skip with a missing-key "
            f"reason rather than calling {args.target}. Set it in the repo-root .env."
        )

    _safe_print(f"\n== migrating {_baseline_count(store)} imported prompt(s) -> {args.target} ==")
    scored = 0

    def progress(row: RowResult) -> None:
        nonlocal scored
        scored += 1
        _safe_print(f"  ({scored}) [{row.status:^7}] {(row.category or '-'):<9} {row.prompt_preview[:55]}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as http:
        comparators = build_comparators(args.compare, judge_model=args.judge_model, http=http)
        report = await run_migration(
            store, args.target, comparators,
            target_provider=args.target_provider, concurrency=4, progress=progress,
        )

    pricing = []
    if args.pricing:
        from agentrec.pricing import PricingCatalog, price_report
        catalog = PricingCatalog.load()
        pricing = [price_report(report, catalog.profile(args.pricing), as_of="latest")]

    _safe_print("")
    _safe_print(render_console(report, pricing=pricing))

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    base = reports_dir / default_report_basename(f"{args.target}-imported")
    renderers = {".html": render_html, ".md": render_markdown}
    suffixes = {"html": (".html",), "md": (".md",), "all": (".md", ".html")}[args.format]
    for suffix in suffixes:
        # base.name + suffix (not with_suffix): dot-safe for ids like claude-haiku-4-5.
        path = base.parent / (base.name + suffix)
        path.write_text(renderers[suffix](report, pricing=pricing), encoding="utf-8")
        _safe_print(f"Report written: {path}")

    if args.strict and not report.strict_passed:
        _safe_print("\nstrict gate: FAILED")
        return 1
    return 0


def _guess_provider(model: str) -> str:
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "o1", "o3", "o4", "text-")):
        return "openai"
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith(("mistral", "magistral", "ministral", "open-mistral", "open-mixtral")):
        return "mistral"
    return "openai"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=None, help="import this export instead of the generated one")
    parser.add_argument("--source", default="auto", help="langfuse|langsmith|otel|auto (default: auto)")
    parser.add_argument("--target", default="claude-haiku-4-5", help="migration target model")
    parser.add_argument("--target-provider", default=None, help="override provider inferred from --target")
    parser.add_argument("--compare", default="exact,fuzzy", help="comparators for --migrate")
    parser.add_argument("--judge-model", default="claude-opus-4-8", help="model for the judge comparator")
    parser.add_argument("--migrate", action="store_true", help="re-ask the target live (costs money)")
    parser.add_argument("--pricing", default=None, help="pricing profile, e.g. 'anthropic-list+openai-list'")
    parser.add_argument("--strict", action="store_true", help="exit 1 if the migrated run fails the gate")
    parser.add_argument(
        "--format", choices=("html", "md", "all"), default="html",
        help="report format(s) to write (default: html)",
    )
    args = parser.parse_args()

    # --- Phase 1: get an export -------------------------------------------
    if args.input:
        export = Path(args.input)
        _safe_print(f"importing your export : {export}")
    else:
        count = write_export()
        export = EXPORT_PATH
        _safe_print(f"generated export : {export}  ({count} records, deliberately messy)")

    # --- Phase 2: import into a hardened store ----------------------------
    store = hardened_store()
    _safe_print(f"corpus dir       : {CORPUS_DIR}")
    summary = await import_corpus(export, store, source=args.source, category="prod-traffic")
    _safe_print(
        f"\n== import summary ==  source={summary.source}  "
        f"imported={summary.imported_count}  skipped={summary.skipped_count}"
    )
    for cid in summary.imported:
        _safe_print(f"  + {cid}")
    for ref, reason in summary.skipped:
        _safe_print(f"  ! skipped {ref}: {reason}")

    if summary.imported_count == 0:
        _safe_print("\nNothing imported — check --source and the export shape.")
        return 1

    # --- Phase 3: inspect what landed ------------------------------------
    await inspect_corpus(store)

    # --- Phase 4: the offline trap (no keys) -----------------------------
    await offline_preview(store, args.target)

    # --- Phase 5: optional live migration --------------------------------
    if args.migrate:
        return await migrate(store, args)

    _safe_print(
        "\nDone (offline). Add --migrate to re-ask the target and render the report:\n"
        f"  .venv\\Scripts\\python.exe examples\\import_observability_export.py --migrate"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
