"""
Grow the corpus on disk.

Records a batch of live streaming OpenAI interactions into a FileStore, so the
corpus persists between runs and accumulates.  Each run tags its interactions
with a short run id, so re-running this script keeps growing the corpus rather
than overwriting it.

Run from the project root:

    .venv\\Scripts\\python.exe examples\\grow_corpus.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

from agentrec import FileStore, RecordingTransport

load_dotenv()

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"

# A batch of more substantial prompts.  Each produces a multi-chunk streamed
# response, so the captured cassettes are non-trivial.  (slug, model, prompt)
JOBS = [
    (
        "twos-complement",
        "gpt-4o-mini",
        "In three sentences, explain why two's complement is the standard way "
        "to represent signed integers in hardware.",
    ),
    (
        "fib-iterative",
        "gpt-4o-mini",
        "Write a Python function that returns the nth Fibonacci number "
        "iteratively, then state its time and space complexity in one line.",
    ),
    (
        "locking-tradeoffs",
        "gpt-4o-mini",
        "Compare optimistic and pessimistic locking for a high-contention bank "
        "ledger. Give one concrete tradeoff for each approach.",
    ),
    (
        "deadlock-haiku",
        "gpt-4o",
        "Write a haiku about a database deadlock discovered at 3am, then add "
        "one sentence explaining the metaphor.",
    ),
]


async def record_one(store: FileStore, iid: str, model: str, prompt: str) -> str:
    inner = httpx.AsyncHTTPTransport()
    transport = RecordingTransport(inner=inner, store=store, key=iid)
    content = ""
    async with httpx.AsyncClient(transport=transport, timeout=60.0) as http_client:
        client = AsyncOpenAI(http_client=http_client)
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
    return content


async def main() -> None:
    store = FileStore(CORPUS_DIR)
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]

    print(f"corpus dir : {CORPUS_DIR}")
    print(f"on disk before this run: {len(store)} interactions")
    print(f"run id     : {run_id}\n")

    for slug, model, prompt in JOBS:
        iid = f"{slug}__{run_id}"
        content = await record_one(store, iid, model, prompt)
        interaction = await store.load(iid)  # read back from disk
        path = store._path(iid)
        size_kb = path.stat().st_size / 1024
        preview = " ".join(content.split())[:70]
        print(f"  + {iid}")
        print(f"      {model:<11} | {len(interaction.chunks):>3} chunks | "
              f"{size_kb:5.1f} KB on disk")
        print(f"      reply: {preview}...")
        print(f"      corpus now holds {len(store)} interactions\n")

    print(f"done. corpus on disk: {len(store)} interactions in {CORPUS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
