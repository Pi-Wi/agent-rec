"""
Migrate a **multi-turn** tool-using agent, scoring each step the model takes.

The earlier tool-calling examples record one decision per prompt. Real agents
loop: look something up, read the result, decide the next action, act, then
reply. agentrec evaluates that **step-wise** — each turn of the loop is recorded
as its own cassette (its own request, carrying the whole conversation so far),
so a 4-turn investigation becomes 4 independently-scored rows. The migration
question per row is sharp: *given the conversation up to this point — including
the baseline's own earlier tool calls and the tool results it saw — does the new
model take the same next action?* Holding that history fixed isolates one
decision per row; it deliberately does **not** re-drive the loop on the target's
own (possibly diverging) trajectory.

This records a small customer-support agent on OpenAI that resolves delivery
complaints by investigating before acting (``look_up_order`` ->
``get_shipping_events`` -> ``issue_refund`` / ``escalate_to_human`` -> reply to
the customer), then migrates the whole transcript to a Claude target. Tool
results are **canned** (a fixed fake back-end) so the loop is reproducible and a
re-run replays instead of paying again — agentrec never executes recorded tools
anyway; it compares what each model *decided to do*.

The two comparators do complementary work across the turns:
``toolcalls`` scores the tool-calling steps (same tool? same arguments?), while
``fuzzy`` scores the closing customer reply (a text turn, where both models
abstain from tools so ``toolcalls`` passes trivially). Add ``judge`` to
``--compare`` to grade the reply semantically.

Run from the project root (needs OPENAI_API_KEY to record and ANTHROPIC_API_KEY
to migrate — both read from the repo-root ``.env``)::

    .venv\\Scripts\\python.exe examples\\multi_turn_agent_migration.py

Flags::

    --target MODEL     migration target (default: claude-haiku-4-5)
    --model MODEL      baseline model to record (default: gpt-4o-mini)
    --compare SPEC     comparators (default: toolcalls,fuzzy)
    --skip-record      reuse the existing corpus, just run the migration
    --format FMT       report format: html (default), md, or all
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Allow `python examples/multi_turn_agent_migration.py` from the repo root
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
CORPUS_DIR = ROOT / "corpus-agent"

# The policy is spelled out so both models have a determinate "right" next
# action at each step — where they nonetheless diverge is exactly the finding a
# migration report should surface.
SYSTEM = (
    "You are a customer-support agent that resolves delivery and order complaints "
    "by investigating with tools before acting, one step at a time. Follow this "
    "policy:\n"
    "1. Always call look_up_order first to get the order's status and tracking.\n"
    "2. If tracking says the order was delivered but the customer says it was not, "
    "call get_shipping_events to check the delivery record. If the events confirm "
    "delivery, do NOT issue a refund automatically — call escalate_to_human for a "
    "manual review (priority 'medium').\n"
    "3. If there is a clear fulfillment error (the wrong item was shipped), call "
    "issue_refund for the order total, with a short reason.\n"
    "4. When the investigation is finished, stop calling tools and reply to the "
    "customer directly in one or two sentences."
)

# OpenAI function-tool definitions (the dialect we record in). agentrec extracts
# these into its neutral form and re-emits them as Anthropic tool definitions on
# migration.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "look_up_order",
            "description": "Look up an order's status, tracking number and contents.",
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
            "name": "get_shipping_events",
            "description": "Get the carrier's scan history for a tracking number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tracking_number": {"type": "string", "description": "The carrier tracking number"},
                },
                "required": ["tracking_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Refund an order when there is a clear fulfillment error.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order id to refund"},
                    "amount": {"type": "number", "description": "Amount to refund"},
                    "reason": {"type": "string", "description": "Why the refund is being issued"},
                },
                "required": ["order_id", "amount", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Queue the case for a human agent's manual review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order id under review"},
                    "summary": {"type": "string", "description": "One-line summary for the human"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "How urgent the review is",
                    },
                },
                "required": ["order_id", "summary", "priority"],
            },
        },
    },
]

# A fixed fake back-end. Keying results off the order id / tracking number keeps
# the loop deterministic regardless of which arguments the model phrases, so the
# transcript is reproducible and re-runs replay for free.
ORDERS = {
    "A1043": {
        "order_id": "A1043",
        "status": "delivered",
        "tracking": "1Z999AA10123456784",
        "item": "wireless earbuds",
        "total": 49.99,
        "currency": "USD",
        "placed": "2026-06-08",
    },
    "B2299": {
        "order_id": "B2299",
        "status": "delivered",
        "tracking": "1Z999AA20999888777",
        "item_shipped": "jacket, red, large",
        "item_ordered": "jacket, blue, medium",
        "total": 79.00,
        "currency": "USD",
        "placed": "2026-06-05",
    },
}
SHIPPING = {
    "1Z999AA10123456784": {
        "tracking": "1Z999AA10123456784",
        "events": [
            {"date": "2026-06-09", "status": "in transit"},
            {"date": "2026-06-11", "status": "out for delivery"},
            {"date": "2026-06-11", "status": "delivered, left at front desk"},
        ],
    },
}

# (category, opening customer message). Each scenario is one multi-turn agent
# loop; every turn within it becomes its own scored migration row.
SCENARIOS: list[tuple[str, str]] = [
    (
        "lost-package",
        "Order #A1043 shows as delivered in tracking, but I never received it. "
        "I'd like a refund please.",
    ),
    (
        "wrong-item",
        "I ordered a blue medium jacket (order #B2299) but received a red large "
        "one instead. I just want my money back.",
    ),
]

MAX_TURNS = 6  # guard against an agent that never stops calling tools


def _safe_print(text: str) -> None:
    """Print without crashing on a non-cp1252 console (Windows default)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(text.encode(enc, "replace").decode(enc, "replace"))


def _args(arguments_json: str | None) -> dict:
    try:
        return json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        return {}


def run_tool(name: str, arguments_json: str | None) -> str:
    """The fake back-end. Returns a JSON string (OpenAI tool messages are text)."""
    args = _args(arguments_json)
    if name == "look_up_order":
        oid = str(args.get("order_id", "")).lstrip("#").strip()
        return json.dumps(ORDERS.get(oid, {"error": "order not found", "order_id": oid}))
    if name == "get_shipping_events":
        tn = str(args.get("tracking_number", "")).strip()
        return json.dumps(SHIPPING.get(tn, {"error": "no scans for tracking number", "tracking": tn}))
    if name == "issue_refund":
        return json.dumps({"refund_id": "RF-8830", "amount": args.get("amount"), "status": "processed"})
    if name == "escalate_to_human":
        return json.dumps({"ticket_id": "ESC-5521", "priority": args.get("priority", "medium"), "queued": True, "eta_hours": 24})
    return json.dumps({"error": f"unknown tool: {name}"})


async def run_agent(http: httpx.AsyncClient, store: FileStore, model: str, category: str, opening: str) -> int:
    """Drive one agent loop, recording each turn as its own cassette.

    Each ``create`` call sends the conversation so far (system + customer +
    every prior assistant turn and tool result), so its request fingerprint —
    and thus its ``semantic_key`` — is distinct from the other turns: agentrec
    files each step as a separate row. The assistant message and tool result are
    appended back into ``messages`` exactly as a real agent runtime would, which
    is what makes the *next* recorded turn a faithful continuation.
    """
    client = AsyncOpenAI(http_client=http)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": opening},
    ]
    for turn in range(1, MAX_TURNS + 1):
        async with cassette(store, mode="auto", metadata={"category": category}):
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        msg = resp.choices[0].message

        assistant: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant)

        if not msg.tool_calls:
            _safe_print(f"    turn {turn}: reply -> {(msg.content or '').strip()[:70]}")
            return turn

        for tc in msg.tool_calls:
            result = run_tool(tc.function.name, tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            _safe_print(f"    turn {turn}: {tc.function.name}({(tc.function.arguments or '').strip()})")

    _safe_print(f"    (stopped after {MAX_TURNS} turns)")
    return MAX_TURNS


async def record_corpus(store: FileStore, model: str) -> None:
    http = async_client(timeout=httpx.Timeout(60.0))
    async with http:
        for category, opening in SCENARIOS:
            _safe_print(f"  [{category}] {opening}")
            turns = await run_agent(http, store, model, category, opening)
            _safe_print(f"    -> {turns} turns recorded\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="claude-haiku-4-5", help="migration target model")
    parser.add_argument("--model", default="gpt-4o-mini", help="baseline model to record")
    parser.add_argument("--compare", default="toolcalls,fuzzy", help="comparator spec")
    parser.add_argument("--skip-record", action="store_true", help="reuse existing corpus")
    parser.add_argument("--judge-model", default="claude-opus-4-8", help="model for the judge comparator")
    parser.add_argument(
        "--format", choices=("html", "md", "all"), default="html",
        help="report format(s) to write (default: html)",
    )
    args = parser.parse_args()

    store = FileStore(CORPUS_DIR)
    print(f"corpus dir : {CORPUS_DIR}")
    print(f"baseline   : {args.model}  ({len(SCENARIOS)} agent transcripts)")
    print(f"target     : {args.target}")
    print(f"comparators: {args.compare}\n")

    if not args.skip_record:
        print("== Recording multi-turn agent transcripts (OpenAI) ==")
        await record_corpus(store, args.model)
    else:
        print("== Skipping record; reusing existing corpus ==\n")

    print(f"== Migrating each turn -> {args.target} and scoring ==")
    # Each recorded turn is one row. `toolcalls` scores the tool-calling steps;
    # `fuzzy` (and `judge`, if added) score the closing customer reply. The
    # comparator http client is only used if `--compare` includes judge/embedding.
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as comparator_http:
        comparators = build_comparators(
            args.compare, judge_model=args.judge_model, http=comparator_http
        )
        report = await run_migration(store, args.target, comparators, concurrency=4)

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    base = reports_dir / default_report_basename(f"{args.target}-agent")
    renderers = {".html": render_html, ".md": render_markdown}
    suffixes = {"html": (".html",), "md": (".md",), "all": (".md", ".html")}[args.format]
    print()
    _safe_print(render_console(report))
    for suffix in suffixes:
        # base.name + suffix (not with_suffix): dot-safe for ids like claude-haiku-4-5.
        path = base.parent / (base.name + suffix)
        path.write_text(renderers[suffix](report), encoding="utf-8")
        _safe_print(f"\nReport written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
