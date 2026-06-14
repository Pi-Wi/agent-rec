"""
Migrate a tool-calling agent step cross-provider, then score *tool selection*.

The migration question for an agent isn't "does the prose match" — it's "given
this conversation, does the new model reach for the same tool, with the same
arguments?" This example records a handful of one-step agent decisions against
OpenAI (a weather tool the model may or may not call), migrates them to a Claude
target, and scores them with the offline ``toolcalls`` comparator. Recorded
tools are **never executed**: agentrec compares what each model *decided to do*,
not what the tool would have returned.

Two of the prompts should trigger a ``get_weather`` call (with differing
arguments), and one deliberately should not — "didn't reach for a tool" is a
behaviour worth confirming holds after a model swap, so it scores as a pass when
both sides abstain.

Run from the project root (needs OPENAI_API_KEY to record and ANTHROPIC_API_KEY
to migrate — both read from the repo-root ``.env``)::

    .venv\\Scripts\\python.exe examples\\tool_calling_migration.py

Flags::

    --target MODEL     migration target (default: claude-haiku-4-5)
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

# Allow `python examples/tool_calling_migration.py` from the repo root without
# an editable install.
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
CORPUS_DIR = ROOT / "corpus-tools"

SYSTEM = (
    "You are a weather assistant. Use the get_weather tool when the user asks "
    "about current conditions. For anything else, just answer in one sentence."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                    },
                },
                "required": ["city"],
            },
        },
    }
]

# (category, prompt). The first two should call get_weather; the third should
# not (it's general knowledge), so both sides abstaining counts as agreement.
PROMPTS: list[tuple[str, str]] = [
    ("tool", "What's the weather in Copenhagen right now? Use celsius."),
    ("tool", "Is it raining in Tokyo at the moment?"),
    ("no_tool", "What's the capital of France?"),
]


def _safe_print(text: str) -> None:
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
            _safe_print(f"  [{category:>7}] {prompt}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="claude-haiku-4-5", help="migration target model")
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
        print("== Recording tool-calling baseline ==")
        await record_corpus(store, args.model)
        print()
    else:
        print("== Skipping record; reusing existing corpus ==\n")

    print(f"== Migrating -> {args.target} and scoring tool selection ==")
    # `toolcalls` is offline (no API call); `judge` would also score the rare
    # text-only abstention rows, but we keep this example key-light.
    comparators = build_comparators("toolcalls")
    report = await run_migration(store, args.target, comparators, concurrency=4)

    base = ROOT / default_report_basename(f"{args.target}-tools")
    renderers = {".html": render_html, ".md": render_markdown}
    suffixes = {"html": (".html",), "md": (".md",), "all": (".md", ".html")}[args.format]
    print()
    _safe_print(render_console(report))
    for suffix in suffixes:
        path = base.with_suffix(suffix)
        path.write_text(renderers[suffix](report), encoding="utf-8")
        _safe_print(f"\nReport written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
