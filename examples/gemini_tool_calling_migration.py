"""
Migrate a tool-calling support agent from OpenAI to **Gemini**, then score the
tool decisions.

A real-world migration question: you run a customer-support agent on
``gpt-4o-mini`` with function calling — it decides whether to look up an order,
issue a refund, escalate to a human, or just answer. Gemini 2.5 Flash is cheaper
and faster, but before you switch you need to know: *on the same tickets, does
Gemini reach for the same tools, with the same arguments?* Getting a refund
decision wrong is not a "the prose differs a little" problem.

This records a handful of one-step agent decisions against OpenAI, migrates them
to a Gemini target, and scores them with the offline ``toolcalls`` comparator
(tool selection + arguments, never the prose). Recorded tools are **never
executed**: agentrec compares what each model *decided to do*, not what the tool
would have returned. The prompts are crafted so each of the three tools is the
right call for a different ticket, plus one FAQ that needs no tool at all — and
"both models abstained" counts as agreement, because *not* reaching for a tool
is behaviour worth confirming holds after a swap.

Direction note: agentrec records at the httpx layer, but the Gemini SDK doesn't
route through httpx, so Gemini traffic can't be *recorded* — Gemini is used here
as the migration **target**. If you're going the other way (already on Gemini,
evaluating GPT/Claude), bring your Gemini traffic in with ``agentrec import``
(Langfuse / LangSmith / OpenTelemetry export) and migrate that corpus instead.

Run from the project root (needs OPENAI_API_KEY to record and GEMINI_API_KEY —
or GOOGLE_API_KEY — to migrate, both read from the repo-root ``.env``)::

    .venv\\Scripts\\python.exe examples\\gemini_tool_calling_migration.py

Flags::

    --target MODEL     migration target (default: gemini-2.5-flash)
    --model MODEL      baseline model to record (default: gpt-4o-mini)
    --skip-record      reuse the existing corpus, just run the migration
    --format FMT       report format: html (default), md, or all
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Allow `python examples/gemini_tool_calling_migration.py` from the repo root
# without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentrec import FileStore, async_client, build_comparators, cassette  # noqa: E402
from agentrec.migration import run_migration  # noqa: E402
from agentrec.report import (  # noqa: E402
    default_report_basename,
    render_console,
    render_html,
    render_markdown,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus-support"

SYSTEM = (
    "You are a customer-support triage agent. Decide the single best action:\n"
    "- Use look_up_order when the customer asks about the status or location of "
    "a specific order.\n"
    "- Use issue_refund when the customer clearly asks for their money back for a "
    "specific order (include a short reason).\n"
    "- Use escalate_to_human when the customer is angry, threatens to leave, or "
    "the issue is repeated/unresolved — set priority accordingly.\n"
    "- For general questions (hours, policies), do NOT call a tool; answer in one "
    "short sentence."
)

# OpenAI function-tool definitions (the dialect we record in).  The neutral form
# agentrec extracts translates to Gemini's functionDeclarations on migration.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "look_up_order",
            "description": "Look up the status and location of a customer's order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order id, e.g. A1043"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Issue a refund for an order the customer is unhappy with.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order id to refund"},
                    "reason": {"type": "string", "description": "Why the refund is being issued"},
                },
                "required": ["order_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Hand the conversation to a human support agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "One-line summary for the human"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "How urgent the escalation is",
                    },
                },
                "required": ["summary", "priority"],
            },
        },
    },
]

# (category, prompt).  Each of the three tools is the right call for one ticket;
# the last needs no tool, so both models abstaining counts as agreement.
PROMPTS: list[tuple[str, str]] = [
    ("lookup", "Where is my order #A1043? It was supposed to arrive two days ago."),
    ("lookup", "Hi, can you check the status of order #C7781 for me?"),
    ("refund", "My blender (order #B2299) stopped working after two uses. I want a refund."),
    (
        "escalate",
        "This is the THIRD time my account data is wrong and nobody has fixed it. "
        "I want to speak to a manager right now.",
    ),
    ("no_tool", "What are your customer-support hours?"),
]


def _safe_print(text: str) -> None:
    """Print without crashing on a non-cp1252 console (Windows default)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(text.encode(enc, "replace").decode(enc, "replace"))


async def record_one(http: httpx.AsyncClient, model: str, prompt: str) -> None:
    client = AsyncOpenAI(http_client=http)
    await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        tools=TOOLS,
        tool_choice="auto",
    )


async def record_corpus(store: FileStore, model: str) -> None:
    http = async_client(timeout=httpx.Timeout(60.0))
    async with http:
        for category, prompt in PROMPTS:
            async with cassette(store, mode="auto", metadata={"category": category}):
                await record_one(http, model, prompt)
            _safe_print(f"  [{category:>8}] {prompt}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="gemini-2.5-flash", help="migration target model")
    parser.add_argument("--model", default="gpt-4o-mini", help="baseline model to record")
    parser.add_argument("--skip-record", action="store_true", help="reuse existing corpus")
    parser.add_argument(
        "--format", choices=("html", "md", "all"), default="html",
        help="report format(s) to write (default: html)",
    )
    args = parser.parse_args()

    store = FileStore(CORPUS_DIR)
    print(f"corpus dir : {CORPUS_DIR}")
    print(f"baseline   : {args.model}  ({len(PROMPTS)} agent steps)")
    print(f"target     : {args.target}\n")

    if not args.skip_record:
        print("== Recording tool-calling baseline (OpenAI) ==")
        await record_corpus(store, args.model)
        print()
    else:
        print("== Skipping record; reusing existing corpus ==\n")

    print(f"== Migrating -> {args.target} and scoring tool selection ==")
    # `toolcalls` is offline (no API call beyond the live target answers, which
    # are cached back into the corpus). It scores which tool each model chose and
    # with what arguments; two responses that both call nothing pass trivially.
    comparators = build_comparators("toolcalls")
    report = await run_migration(store, args.target, comparators, concurrency=4)

    # Reports go in a dedicated folder; paths are built by string concatenation
    # (not Path.with_suffix): a target id like "gemini-2.5-flash" contains a dot,
    # which with_suffix would mistake for an extension and truncate.
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    base = reports_dir / default_report_basename(f"{args.target}-support")
    renderers = {".html": render_html, ".md": render_markdown}
    suffixes = {"html": (".html",), "md": (".md",), "all": (".md", ".html")}[args.format]
    print()
    _safe_print(render_console(report))
    for suffix in suffixes:
        path = base.parent / (base.name + suffix)
        path.write_text(renderers[suffix](report), encoding="utf-8")
        _safe_print(f"\nReport written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
