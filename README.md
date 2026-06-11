# agentrec

Framework-agnostic record/replay for LLM API interactions — plus a
**model-migration report** built on the recorded corpus.

Recording happens at the **httpx transport layer**, below the OpenAI SDK, the
Anthropic SDK, LangChain, or any other httpx-backed client. The core depends
on nothing but `httpx`.

> **Status:** beta (0.2). Record/replay is proven for streaming (SSE) and
> non-streaming (JSON) responses on OpenAI and Anthropic; the API may still
> change in minor releases before 1.0. Migration translation covers
> OpenAI ↔ Anthropic, text-only conversations — tools/images become
> clearly-reasoned skipped rows.

## Install

```bash
pip install agentrec                 # core is httpx-only
pip install "agentrec[compression]"  # + brotli/zstd cassette decoding
```

## Quick start

Build one `agentrec.async_client()`, hand it to your SDK, and wrap calls in a
`cassette`: `mode="auto"` replays a request if it's been recorded, otherwise
records it.

```python
import agentrec
from openai import AsyncOpenAI

store = agentrec.FileStore("corpus")
http = agentrec.async_client()          # honours the active cassette scope
oai = AsyncOpenAI(http_client=http)

@agentrec.cassette(store, mode="auto")  # recorded once, replayed thereafter
async def ask(prompt: str) -> str:
    response = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
```

Streaming works identically — the raw SSE bytes are recorded and the SDK
parser re-runs on replay. `cassette` also works as an async context manager,
and the same client plugs into the Anthropic SDK unchanged:
`AsyncAnthropic(http_client=http)`.

Synchronous SDKs use the same seam: build `agentrec.sync_client()`, hand it
to `OpenAI(http_client=...)` / `Anthropic(http_client=...)`, and use
`cassette` as a plain `with` block or decorator on a sync function.

Prefer wiring httpx yourself? Use the transports directly:

```python
from agentrec import RecordingTransport, ReplayTransport

httpx.AsyncClient(transport=RecordingTransport(httpx.AsyncHTTPTransport(), store))
httpx.AsyncClient(transport=ReplayTransport(store))   # offline; cannot touch the network
```


## Model-migration report

Every recording carries provenance: `provider`, `model`, and a
`semantic_key` — a hash of the provider-neutral conversation (system +
messages), so the same prompt recorded against different models, different
providers, or different sampling parameters groups together. The migration
runner re-asks every corpus prompt of a **target model** (cross-provider
translation included: an OpenAI-recorded prompt can be re-asked of Claude),
caches the answers back into the corpus, and scores baseline vs. target:

| Comparator  | Needs network? | What it measures                                  |
| ----------- | -------------- | ------------------------------------------------- |
| `exact`     | no             | normalized string equality (classification-style) |
| `fuzzy`     | no             | `difflib` sequence similarity                     |
| `embedding` | OpenAI API     | cosine similarity of embeddings                   |
| `judge`     | LLM API        | an LLM scores semantic equivalence                |

```bash
agentrec migrate  --corpus corpus --target claude-haiku-4-5 --compare exact,fuzzy,judge
agentrec report   --corpus corpus --target claude-haiku-4-5 --strict   # offline re-render; CI gate
agentrec annotate --corpus corpus                                      # backfill summaries/metadata
```

Re-runs are cheap: answered prompts are served from disk, rate-limited calls
retry with backoff, and failures are never cached. Rows are scored
concurrently (`--concurrency`). Recordings tagged with a category —
`cassette(store, metadata={"category": "extract"})` — get a per-category
breakdown in the report, with output-token columns that surface
verbosity/cost differences between the models.

## How it works

```
agentrec/
  capture.py      # storage-agnostic captured request/response data
  keying.py       # request fingerprint → provider / model / semantic_key / cassette id
  store.py        # InMemoryStore + FileStore (human-readable JSON cassettes)
  transport.py    # RecordingTransport / ReplayTransport / AutoTransport
  session.py      # async_client() + cassette — the ergonomic seam
  providers/      # OpenAI + Anthropic request/response dialects
  comparators.py  # exact / fuzzy / embedding / judge response scoring
  migration.py    # run_migration() — replay the corpus against a candidate model
  report.py       # Markdown / HTML / console rendering
  cli.py          # agentrec migrate | report | annotate
```

- **Tee, don't buffer:** the caller and the store see every chunk in order,
  live — the recorder never holds back the stream.
- **Raw bytes, no parsing:** cassettes store the original byte frames; the SDK
  parser re-runs on replay, so one codebase covers every provider.
- **Replay mode can't leak:** `ReplayTransport` (`mode="replay"`) has no inner
  transport, so it cannot accidentally hit the network — use it when you need
  a hard offline guarantee (CI). Note that `mode="auto"` *does* make a live
  call (and records it) whenever a request has no recording yet — e.g. after
  a prompt edit changes the fingerprint.
- **Failures aren't cached:** non-2xx responses are never recorded by default,
  so a transient 429/500 can't be replayed forever as the answer
  (`record_errors=True` opts in deliberately).
- **Request-derived keys:** interactions are keyed by a fingerprint
  (method + path + model + normalised body), so identical calls replay
  deterministically. The `semantic_key` that groups prompts for the migration
  report is derived from the provider-neutral conversation instead — same
  prompt against OpenAI or Anthropic, at any temperature, groups together.
- **Best-effort secret hygiene:** `FileStore` always redacts auth headers, and
  scrubs *known* secret shapes from request bodies and summaries before
  anything touches disk. This is a safety net, not a guarantee — response
  bodies are stored verbatim unless you opt in via `scrub_response_body=True`,
  and unknown secret formats pass through. Review cassettes before sharing a
  corpus; extend `secret_patterns=[...]` with your organisation's shapes.

Any SDK that accepts an httpx client works. Non-httpx SDKs (boto3/Bedrock,
some Vertex paths) never route through the transport, so they need a
different seam.

## Tests

```bash
pytest -q
```

The suite is offline by default: canned SSE/JSON fixtures, with accidental
network access failing the test. Live record→replay tests run only when
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` are present (read from a project-root
`.env`) and skip cleanly otherwise.

## Attributions

See [NOTICE](NOTICE) for third-party acknowledgements, including inspiration
from **baml_vcr** for the streaming chunk capture/replay pattern.
