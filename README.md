# agentrec

Framework-agnostic record/replay for streaming LLM API interactions.
Records and replays at the **httpx transport layer**, so it works below
the OpenAI SDK, the Anthropic SDK, LangChain, or any other httpx-backed client —
the core depends on nothing but `httpx`.

> **Status:** prototype. The record/replay mechanic is proven for streaming
> (SSE) and non-streaming (JSON) responses, for both OpenAI and Anthropic.
> On top of the recorded corpus sits a working **model-migration report**
> (see [Model-migration report](#model-migration-report)).

---

## Architecture

```
agentrec/
  capture.py      # CapturedChunk, CapturedRequest, CapturedInteraction — storage-agnostic data
  keying.py       # fingerprint() — provider/model/semantic_key + the default cassette id
  store.py        # InteractionStore ABC + InMemoryStore + FileStore (JSON cassettes)
  transport.py    # RecordingTransport, ReplayTransport, AutoTransport (the low-level seam)
  session.py      # async_client() + cassette — the high-level, ergonomic seam
  providers/      # ProviderAdapter registry: OpenAI + Anthropic request/response dialects
  comparators.py  # exact / fuzzy (offline), embedding / judge (live) response scoring
  migration.py    # run_migration() — replay the corpus against a candidate model
  report.py       # Markdown / HTML / console rendering of a MigrationReport
  cli.py          # `agentrec migrate | report | annotate`
```

Key design commitments:

- **Tee, don't intercept-and-buffer.** `RecordingTransport` wraps the live
  stream so the caller and the store both see every chunk in order, without
  the recorder buffering the whole response first.
- **Raw bytes, no parsing.** Chunks are stored as the original SSE byte frames.
  The SDK parser re-runs on replay and produces the same objects it would have
  from the network. OpenAI SSE and Anthropic SSE look identical here — both are
  byte streams — which is why one codebase covers both with no provider branches.
- **Injected store.** `InMemoryStore` (volatile) and `FileStore` (human-readable
  JSON cassettes, atomic writes, secret-scrubbing) both satisfy `InteractionStore`.
  A future store (Parquet corpus, S3, …) drops in without touching transport code.
- **Distinct transport classes.** `RecordingTransport` requires an inner
  transport; `ReplayTransport` has none — it *cannot* accidentally touch the
  network. `AutoTransport` composes the two for cassette semantics.
- **Request-derived keys.** Each interaction is keyed by a fingerprint of the
  request (method + path + model + normalised body), so one transport handles
  many distinct calls and the same call replays deterministically.

---

## Install

```bash
pip install -e ".[dev]"     # core is httpx-only; the dev extra adds the SDKs + pytest
```

---

## Quick start — the high-level seam

Build one `agentrec.async_client()` and pass it to any httpx-based SDK. Wrap
your calls in a `cassette`: `mode="auto"` replays a request if it's been
recorded, otherwise records it (true VCR-style cassette behaviour).

```python
import agentrec
from openai import AsyncOpenAI

store = agentrec.FileStore("corpus")
http = agentrec.async_client()              # honours the active cassette scope
oai = AsyncOpenAI(http_client=http)

# Streaming — every call inside is recorded once, then replayed:
@agentrec.cassette(store, mode="auto")
async def ask_stream(prompt: str) -> str:
    stream = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    out = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            out += chunk.choices[0].delta.content
    return out

# Non-streaming — works identically; the JSON body is one chunk at the transport layer:
@agentrec.cassette(store, mode="auto")
async def ask(prompt: str) -> str:
    response = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content

# Or as a context manager:
async with agentrec.cassette(store, mode="record"):
    await oai.chat.completions.create(...)
```

The same `async_client` + `cassette` works against the Anthropic SDK unchanged —
just `AsyncAnthropic(http_client=http)`.

---

## Lower-level seam — explicit transports

When you'd rather wire the httpx client yourself (no contextvar), use the
transports directly. `key` is optional: omit it for request-derived keying, or
pass a fixed id for a single named cassette.

```python
import httpx
from openai import AsyncOpenAI
from agentrec import FileStore, RecordingTransport, ReplayTransport

store = FileStore("corpus")

# --- Record (needs network) ---
async with httpx.AsyncClient(
    transport=RecordingTransport(httpx.AsyncHTTPTransport(), store, key="weather")
) as http_client:
    client = AsyncOpenAI(http_client=http_client)
    stream = await client.chat.completions.create(..., stream=True)
    async for chunk in stream:
        ...   # caller receives the live stream unchanged

# --- Replay (offline, no key needed if you recorded with request keying) ---
async with httpx.AsyncClient(transport=ReplayTransport(store, key="weather")) as http_client:
    client = AsyncOpenAI(http_client=http_client)
    stream = await client.chat.completions.create(..., stream=True)
    async for chunk in stream:
        ...   # identical to the recorded run
```

---

## Provider support

Interception is at the httpx transport, so agentrec is provider-neutral for
**any SDK that lets you pass an httpx client**:

| SDK / client                         | Works | How                                         |
| ------------------------------------ | :---: | ------------------------------------------- |
| OpenAI (`openai`)                    |  ✅   | `AsyncOpenAI(http_client=...)`              |
| Anthropic (`anthropic`)              |  ✅   | `AsyncAnthropic(http_client=...)`           |
| Most modern httpx-based SDKs / LangChain | ✅ | pass the agentrec httpx client through      |
| **Non-httpx SDKs** (AWS Bedrock/boto3, some Vertex paths) | ❌ | they don't route through httpx, so the transport never sees the call — a different seam would be needed |

The boundary is "httpx-backed," not "OpenAI." If a client opens its sockets
through `botocore`/`urllib3` instead of httpx, transport interception can't see
it.

---

## Running the tests

```bash
pytest -q
```

| Test file                | Needs a key? | What it proves                                                    |
| ------------------------ | ------------ | ----------------------------------------------------------------- |
| `tests/test_streaming.py`      | offline + `OPENAI_API_KEY` | OpenAI SSE replay mechanic; live record→replay identity |
| `tests/test_non_streaming.py`  | offline      | Plain JSON (non-streaming) record/replay, auto mode, provenance   |
| `tests/test_filestore.py`      | offline      | FileStore round-trip, redaction, hostile ids, readable cassettes  |
| `tests/test_session.py`        | offline      | `async_client`/`cassette`, auto mode, request keying, metadata    |
| `tests/test_providers.py`      | offline      | Adapter decoding (SSE/JSON × provider), translation, registry     |
| `tests/test_comparators.py`    | offline      | Comparator scoring incl. mocked embedding/judge, spec parsing     |
| `tests/test_migration.py`      | offline      | Migration end-to-end, caching, lineage metadata, report + CLI     |
| `tests/test_anthropic.py`      | offline + `ANTHROPIC_API_KEY` | Anthropic replay (provider-neutrality); live record→replay |
| `tests/test_live_record.py`    | `OPENAI_API_KEY` | live capture against the real OpenAI API                    |

Key-gated tests skip cleanly when the key is absent. Live keys are read from a
project-root `.env` (via `python-dotenv`). The offline tests use canned SSE
frames and patch `httpx.AsyncHTTPTransport` so any accidental network access
fails the test.

---

## Model-migration report

Every recording carries provenance in `interaction.metadata`: `provider`,
`model`, `semantic_key`, and `recorded_at`. The **`semantic_key`** is a hash of
the request *without* the model (and other non-semantic fields), so two
interactions recorded against different models for the same logical prompt share
a `semantic_key`.

The migration runner builds on that: it groups the corpus by `semantic_key`,
re-asks every recorded prompt of a **target model** (cross-provider translation
included — an OpenAI-recorded prompt can be re-asked of Claude), records the
target's answers back into the corpus as `migration__…` cassettes, and scores
baseline vs. target with the selected comparators:

| Comparator  | Needs network? | What it measures                                  |
| ----------- | -------------- | ------------------------------------------------- |
| `exact`     | no             | normalized string equality (classification-style) |
| `fuzzy`     | no             | `difflib` sequence similarity                     |
| `embedding` | OpenAI API     | cosine similarity of embeddings                   |
| `judge`     | LLM API        | an LLM scores semantic equivalence                |

```bash
# Re-ask the corpus of a candidate model and write Markdown + HTML reports:
agentrec migrate --corpus corpus --target claude-haiku-4-5 --compare exact,fuzzy,judge

# Re-render fully offline from already-recorded migration cassettes
# (offline comparators only; --strict exits 1 on any failure — a CI gate):
agentrec report --corpus corpus --target claude-haiku-4-5 --strict

# Backfill summary blocks + fingerprint metadata into older cassettes:
agentrec annotate --corpus corpus
```

Re-running `migrate` is cheap: each target answer is itself a cassette, so
already-answered prompts are served from disk and only new prompts hit the API.
A failed (non-200) target call is never cached — a re-run retries it live.

---

## Attributions

See [NOTICE](NOTICE) for third-party acknowledgements, including inspiration
from **baml_vcr** for the streaming chunk capture/replay pattern.
