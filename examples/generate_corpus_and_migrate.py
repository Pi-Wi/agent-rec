"""
End-to-end demo: build a 100-prompt corpus of real OpenAI interactions, then
migrate it cross-provider to a Claude model and render the report.

What it does
------------
1. Records 100 realistic ``gpt-4o-mini`` chat completions into ``corpus/`` via
   agentrec's high-level ``cassette`` seam, each tagged with a ``category``
   (classify / extract / summarize / rewrite / translate) so the report can
   break results down per task type.  Auto mode means a re-run replays the
   already-recorded prompts instead of paying for them again.
2. Runs the migration: every recorded prompt is re-asked of a Claude target
   (cross-provider translation, answers cached back into the corpus, rows
   scored concurrently) and scored with every comparator.
3. Writes the report — HTML by default (``--format md`` / ``--format all``
   for Markdown).

The prompts mirror what production LLM pipelines actually do: classification
(sentiment, routing, priority, spam, language, PII), structured data
extraction from messy text, summarization of tickets/incidents/reviews, text
normalization (grammar, tone, redaction), and localization of UI strings.

Run from the project root (needs OPENAI_API_KEY and, for the migration,
ANTHROPIC_API_KEY — both read from the repo-root ``.env``)::

    .venv\\Scripts\\python.exe examples\\generate_corpus_and_migrate.py

Flags::

    --target MODEL     migration target (default: claude-haiku-4-5)
    --compare SPEC     comparators (default: exact,fuzzy,embedding,judge)
    --model MODEL      baseline model to record (default: gpt-4o-mini)
    --format FMT       report format: html (default), md, or all
    --limit N          only record/migrate the first N prompts (smoke tests)
    --skip-record      reuse the existing corpus, just run the migration
    --concurrency N    parallel requests for recording and scoring (default: 6)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Allow `python examples/generate_corpus_and_migrate.py` from the repo root
# without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentrec import FileStore, async_client, build_comparators, cassette  # noqa: E402
from agentrec.migration import MIGRATION_PREFIX, RowResult, run_migration  # noqa: E402
from agentrec.report import (  # noqa: E402
    default_report_basename,
    render_console,
    render_html,
    render_markdown,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus"

# A system prompt keeps answers short and pipeline-shaped, so baseline and
# target are comparable and cassettes stay small.
SYSTEM = "You are a precise assistant. Answer directly and concisely. No preamble."

# 100 prompts shaped like real production API calls: classification with fixed
# label sets, JSON extraction from messy text, operational summarization, text
# normalization, and UI-string localization.  (category, prompt)
PROMPTS: list[tuple[str, str]] = [
    # --- Classification (30): fixed label sets, the bread and butter ---------
    ("classify", "Sentiment (positive/negative/neutral): 'Shipping was fast but the product broke within a week.'"),
    ("classify", "Sentiment (positive/negative/neutral): 'Absolutely love it, exceeded every expectation!'"),
    ("classify", "Sentiment (positive/negative/neutral): 'It's fine. Does the job, nothing special.'"),
    ("classify", "Sentiment (positive/negative/neutral): 'Third time my delivery is late. I want a refund.'"),
    ("classify", "Route this support ticket (billing/technical/account/shipping): 'I was charged twice this month.'"),
    ("classify", "Route this support ticket (billing/technical/account/shipping): 'The app crashes when I open settings.'"),
    ("classify", "Route this support ticket (billing/technical/account/shipping): 'I can't reset my password.'"),
    ("classify", "Route this support ticket (billing/technical/account/shipping): 'My package shows delivered but never arrived.'"),
    ("classify", "Route this support ticket (billing/technical/account/shipping): 'How do I download my invoices for tax season?'"),
    ("classify", "Priority (low/medium/high/urgent): 'Login is broken for all users in production.'"),
    ("classify", "Priority (low/medium/high/urgent): 'A tooltip on the settings page has a small typo.'"),
    ("classify", "Priority (low/medium/high/urgent): 'Checkout intermittently fails for about 10% of customers.'"),
    ("classify", "Spam or not spam: 'Congratulations! You won a $1000 gift card, click here to claim.'"),
    ("classify", "Spam or not spam: 'Hi Sam, can we move our 2pm meeting to 3pm tomorrow?'"),
    ("classify", "Spam or not spam: 'URGENT: verify your account within 24 hours or it will be suspended.'"),
    ("classify", "Intent (question/complaint/praise/refund_request): 'Why is my order still not here after two weeks?'"),
    ("classify", "Intent (question/complaint/praise/refund_request): 'Your support team solved my issue in minutes!'"),
    ("classify", "Intent (question/complaint/praise/refund_request): 'The blender stopped working after two uses. I want my money back.'"),
    ("classify", "Language of this text (ISO 639-1 code only): 'Wo ist der nächste Bahnhof?'"),
    ("classify", "Language of this text (ISO 639-1 code only): '¿Dónde está la estación de tren?'"),
    ("classify", "Language of this text (ISO 639-1 code only): 'Hvor er nærmeste togstation?'"),
    ("classify", "Topic (billing/bug/feature_request/how_to): 'It would be great if exports supported CSV.'"),
    ("classify", "Topic (billing/bug/feature_request/how_to): 'The dashboard shows a 500 error when filtering by date.'"),
    ("classify", "Topic (billing/bug/feature_request/how_to): 'How do I add a teammate to my workspace?'"),
    ("classify", "Churn risk (low/medium/high): 'We're evaluating alternatives because prices went up again.'"),
    ("classify", "Churn risk (low/medium/high): 'Renewed for another year, the new features are great.'"),
    ("classify", "Is this about a delivery problem? (yes/no): 'The tracking number you sent does not work.'"),
    ("classify", "Does this text contain personal data? (yes/no): 'My SSN is 523-12-9876, please update my file.'"),
    ("classify", "Does this text contain personal data? (yes/no): 'Bad weather in the region delayed all shipments.'"),
    ("classify", "Moderation (allowed/flagged): 'You are an idiot and your product is garbage.'"),

    # --- Data extraction (30): structured JSON out of messy text -------------
    ("extract", "Extract as JSON {name, company}: 'Hi, this is Maria Gonzalez calling from Acme Robotics about the Q3 contract.'"),
    ("extract", "Extract all dates as a JSON array of ISO dates: 'The invoice was issued 2026-03-01 and is due 2026-03-15.'"),
    ("extract", "Extract as JSON {amount, currency}: 'Your total comes to $1,249.99 including tax.'"),
    ("extract", "Extract the email address: 'Reach me at jane.doe+work@example.co.uk anytime.'"),
    ("extract", "Extract as JSON {city, country}: 'Our HQ is in Lyon, France, with a satellite office in Austin.'"),
    ("extract", "Extract the phone number: 'Call our support line at (415) 555-0132 between 9 and 5.'"),
    ("extract", "Extract as JSON {sku, quantity}: 'Please ship 12 units of SKU-44821 to the Hamburg warehouse.'"),
    ("extract", "Extract the action items as a JSON array: 'John will email the report, Lisa books the venue, and we all review the deck by Friday.'"),
    ("extract", "Extract as JSON {flight, gate}: 'Flight UA287 is now boarding at gate B14.'"),
    ("extract", "Extract the order number: 'Hello, I'm writing about order #84412-B which arrived damaged.'"),
    ("extract", "Extract the IBAN: 'Please wire the deposit to IBAN DE89 3704 0044 0532 0130 00 by Friday.'"),
    ("extract", "Extract as JSON {day, time, timezone}: 'Let's sync Thursday at 14:30 CET on the usual bridge.'"),
    ("extract", "Extract all monetary amounts as a JSON array: 'Setup costs $500, then $99 per month, plus a $25 activation fee.'"),
    ("extract", "Extract as JSON {street, zip, city}: 'Send returns to Lagerstrasse 12, 20095 Hamburg, attention Returns Dept.'"),
    ("extract", "Extract the tracking number: 'Your parcel 1Z999AA10123456784 left our facility this morning.'"),
    ("extract", "Extract as JSON {error_code, service} from this log line: '2026-06-11T09:14:02Z payments-api ERROR 5021 connection pool exhausted'"),
    ("extract", "Extract the version number: 'After updating to v2.14.3 the export button disappeared.'"),
    ("extract", "Extract as JSON {employee_id, department}: 'Badge E-20331 belongs to Priya Nair in Procurement.'"),
    ("extract", "Extract the names of all people mentioned as a JSON array: 'Tom and Aisha met with Dr. Keller to review the audit.'"),
    ("extract", "Extract the license plate: 'The delivery van, plate HH-AB 1234, was parked at dock 3.'"),
    ("extract", "Extract as JSON {product, issue}: 'The X200 vacuum's battery drains within ten minutes.'"),
    ("extract", "Extract the invoice number: 'Re: outstanding payment for invoice INV-2026-0457.'"),
    ("extract", "Extract as JSON {checkin, checkout} as ISO dates: 'We'd like the room from March 3rd to March 7th, 2026.'"),
    ("extract", "Extract the discount percentage: 'Use code SPRING for 15% off your first order.'"),
    ("extract", "Extract as JSON {from, to} airport codes: 'Searching flights CPH to JFK for two adults.'"),
    ("extract", "Extract the contract end date as an ISO date: 'The agreement runs through 31 December 2026 with auto-renewal.'"),
    ("extract", "Extract as JSON {temperature_c, sensor}: 'Sensor 7 in the cold room reads -18.5 degrees Celsius.'"),
    ("extract", "Extract the username: 'User @data_wrangler_88 reported the sync issue first.'"),
    ("extract", "Extract the last four card digits: 'The charge went to the Visa ending in 4242.'"),
    ("extract", "Extract all URLs as a JSON array: 'Docs moved to https://docs.example.com/v2; old links via http://example.com/legacy redirect.'"),

    # --- Summarization (15): tickets, incidents, reviews, handovers ----------
    ("summarize", "Summarize this support thread in one sentence: 'Customer reported login failures on mobile, support suggested clearing the cache which did not help, the issue was escalated to engineering who found an expired certificate, a fix was deployed, and the customer confirmed resolution.'"),
    ("summarize", "Summarize in one sentence for a status page: 'Between 09:12 and 10:47 UTC some API requests returned elevated 5xx errors due to a failed database failover; traffic was rerouted and error rates returned to normal.'"),
    ("summarize", "One-sentence executive summary: 'Q2 churn rose from 4% to 6%, driven by small-business accounts citing price increases; enterprise retention stayed flat while expansion revenue grew 9%.'"),
    ("summarize", "Summarize this review in one sentence: 'I have used this laptop for three months. The screen is gorgeous and battery life is solid, but the fan noise under load is noticeable and the webcam is mediocre.'"),
    ("summarize", "TL;DR of these meeting notes in one sentence: 'We agreed to ship the beta on June 20, Maria owns the migration guide, the pricing review moved to next week, and we revisit the SLA discussion after the customer call.'"),
    ("summarize", "One-line summary of this changelog: 'Fixed a memory leak in the upload handler, improved dark-mode contrast, added keyboard shortcuts, deprecated the legacy export format.'"),
    ("summarize", "Summarize the complaint in one sentence: 'I ordered a blue medium jacket but received a red large, the return label link was broken, and support took four days to respond.'"),
    ("summarize", "Summarize for a shift handover in one sentence: 'Night shift saw two failed batch jobs which were rerun successfully, disk usage on db-3 hit 85%, and the vendor confirmed the maintenance window for Saturday.'"),
    ("summarize", "Headline (max 8 words) for this update: 'The mobile app now supports offline mode, letting field technicians complete inspections without connectivity and sync automatically once back online.'"),
    ("summarize", "Summarize this policy in one sentence: 'Employees may work remotely up to three days per week, must be reachable during core hours 10-15, and need manager approval for full-remote arrangements.'"),
    ("summarize", "Summarize the incident impact in one sentence: 'The pricing bug showed VAT-exclusive totals to EU customers for six hours; 214 orders were affected and will be refunded the difference automatically.'"),
    ("summarize", "Condense this email to one sentence: 'Following up on our call - attached is the revised proposal with updated timelines, a 5% volume discount as discussed, and the security questionnaire your IT team requested.'"),
    ("summarize", "Summarize the risk in one sentence: 'While the merger promises cost savings through shared infrastructure, analysts warn that cultural integration and overlapping product lines pose execution risks.'"),
    ("summarize", "Summarize the recurring feedback theme in one sentence: 'Across 80 survey responses, users repeatedly praised onboarding speed but flagged confusing invoice layouts and slow support response on weekends.'"),
    ("summarize", "Summarize this bug report in one sentence: 'Steps: open the editor, paste a table from Excel, undo twice - the app freezes for about 30 seconds and sometimes loses the last paragraph; happens on Windows and macOS since v4.2.'"),

    # --- Rewriting / normalization (15): tone, grammar, redaction ------------
    ("rewrite", "Rewrite politely for a customer email: 'Send me the report now.'"),
    ("rewrite", "Make this more formal: 'Hey, can you take a look at this when you get a sec?'"),
    ("rewrite", "Fix grammar and spelling, return only the corrected text: 'Me and him was going to recieve the package on Wendesday.'"),
    ("rewrite", "Replace all personal data with [REDACTED]: 'Contact Anna Larsen at +45 22 11 33 44 or anna@example.dk for access.'"),
    ("rewrite", "Rewrite in active voice: 'The proposal was reviewed by the committee.'"),
    ("rewrite", "Make this concise (max 10 words): 'Due to the fact that it was raining, we made the decision to postpone the event.'"),
    ("rewrite", "Neutralize the tone for a status update: 'The vendor STILL has not fixed their broken API after three weeks of us begging.'"),
    ("rewrite", "Rewrite for a non-technical audience: 'The outage was caused by an expired TLS certificate on the load balancer.'"),
    ("rewrite", "Turn this into a polite decline: 'No, we won't build that feature.'"),
    ("rewrite", "Normalize this address into one line with proper capitalization: 'lagerstrasse 12 20095 hamburg germany'"),
    ("rewrite", "Rewrite as a single bullet point: 'The meeting covered the hiring plan, the office move, and the holiday schedule.'"),
    ("rewrite", "Remove the filler words: 'So basically we just kind of need to actually finalize the budget like today.'"),
    ("rewrite", "Make this subject line professional: 'wanna chat about the budget thing'"),
    ("rewrite", "Soften this for a performance review: 'Your code is sloppy and full of bugs.'"),
    ("rewrite", "Rewrite this error message to be user-friendly: 'ERR_CONN_5021: pool exhausted at gateway.'"),

    # --- Localization (10): UI strings and canned support replies ------------
    ("translate", "Translate to German: 'Your order has been shipped and will arrive in 3-5 business days.'"),
    ("translate", "Translate to French: 'Your subscription will renew on July 1st.'"),
    ("translate", "Translate to Spanish: 'Click the link below to reset your password.'"),
    ("translate", "Translate to Danish: 'Thank you for contacting support. We will reply within 24 hours.'"),
    ("translate", "Translate to Dutch: 'Your invoice is attached as a PDF.'"),
    ("translate", "Translate to Italian: 'The item is currently out of stock.'"),
    ("translate", "Translate to Portuguese: 'Free shipping on orders over 50 euros.'"),
    ("translate", "Translate to Swedish: 'Your payment could not be processed. Please check your card details.'"),
    ("translate", "Translate to Polish: 'Two-factor authentication is now enabled on your account.'"),
    ("translate", "Translate to Norwegian: 'Your return has been received and your refund is on its way.'"),
]


def _safe_print(text: str) -> None:
    """Print without crashing on a non-cp1252 console (Windows default).

    Model replies can contain characters the terminal's codec can't encode
    (e.g. romaji 'ō'); fall back to an ASCII-safe rendering rather than letting
    a progress line abort a 100-prompt run.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(text.encode(enc, "replace").decode(enc, "replace"))


async def _record_one(http: httpx.AsyncClient, model: str, prompt: str) -> str:
    client = AsyncOpenAI(http_client=http)
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


async def record_corpus(
    store: FileStore, model: str, prompts: list[tuple[str, str]], concurrency: int
) -> None:
    """Record (or replay) each prompt, tagged with its category.

    Auto mode keys each cassette on the request fingerprint, so an interrupted
    run resumes cheaply: prompts already on disk replay, only new ones cost an
    API call.  The per-call ``metadata`` tag is what the migration report's
    category breakdown groups on.
    """
    http = async_client(timeout=httpx.Timeout(60.0))
    semaphore = asyncio.Semaphore(concurrency)
    done = 0
    total = len(prompts)

    async def one(category: str, prompt: str) -> None:
        nonlocal done
        async with semaphore:
            try:
                async with cassette(store, mode="auto", metadata={"category": category}):
                    text = await _record_one(http, model, prompt)
                preview = " ".join(text.split())[:60]
                status = f"  [{category:>9}] {preview}"
            except Exception as exc:  # one bad prompt shouldn't sink the batch
                status = f"  [{category:>9}] ERROR: {exc}"
        done += 1
        _safe_print(f"({done:>3}/{total}) {status}")

    async with http:
        await asyncio.gather(*(one(cat, prompt) for cat, prompt in prompts))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="claude-haiku-4-5", help="migration target model")
    parser.add_argument("--compare", default="exact,fuzzy,embedding,judge", help="comparator spec")
    parser.add_argument("--model", default="gpt-4o-mini", help="baseline model to record")
    parser.add_argument(
        "--format", choices=("html", "md", "all"), default="html",
        help="report format(s) to write (default: html)",
    )
    parser.add_argument("--limit", type=int, default=None, help="only the first N prompts")
    parser.add_argument("--skip-record", action="store_true", help="reuse existing corpus")
    parser.add_argument(
        "--concurrency", type=int, default=6,
        help="parallel requests for recording and scoring",
    )
    parser.add_argument("--judge-model", default="claude-opus-4-8", help="model for the judge comparator")
    parser.add_argument("--out", default=None, help="report output base path")
    args = parser.parse_args()

    prompts = PROMPTS[: args.limit] if args.limit else PROMPTS
    store = FileStore(CORPUS_DIR)

    print(f"corpus dir : {CORPUS_DIR}")
    print(f"baseline   : {args.model}  ({len(prompts)} prompts)")
    print(f"target     : {args.target}")
    print(f"comparators: {args.compare}")
    print(f"on disk before this run: {len(store)} cassettes\n")

    # --- Phase 1: record the baseline corpus -------------------------------
    if not args.skip_record:
        print("== Recording baseline cassettes ==")
        await record_corpus(store, args.model, prompts, args.concurrency)
        print(f"\ncorpus now holds {len(store)} cassettes\n")
    else:
        print("== Skipping record; reusing existing corpus ==\n")

    # --- Phase 2: migrate + score (rows run concurrently) -------------------
    print(f"== Migrating corpus -> {args.target} and scoring ==")
    baseline_total = sum(1 for iid in store.ids() if not iid.startswith(MIGRATION_PREFIX))
    scored = 0

    def progress(row: RowResult) -> None:
        nonlocal scored
        scored += 1
        _safe_print(
            f"({scored:>3}/{baseline_total}) [{row.status:^7}] "
            f"{(row.category or '-'):<9} {row.prompt_preview[:55]}"
        )

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as comparator_http:
        comparators = build_comparators(
            args.compare, judge_model=args.judge_model, http=comparator_http
        )
        report = await run_migration(
            store,
            args.target,
            comparators,
            concurrency=args.concurrency,
            progress=progress,
        )

    # --- Phase 3: render ----------------------------------------------------
    base = Path(args.out) if args.out else ROOT / default_report_basename(args.target)
    renderers = {".html": render_html, ".md": render_markdown}
    suffixes = {"html": (".html",), "md": (".md",), "all": (".md", ".html")}[args.format]
    written = []
    for suffix in suffixes:
        path = base.with_suffix(suffix)
        path.write_text(renderers[suffix](report), encoding="utf-8")
        written.append(path)

    print()
    _safe_print(render_console(report))
    for path in written:
        _safe_print(f"\nReport written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
