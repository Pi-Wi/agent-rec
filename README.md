# agentrec

**Will the new model break my prompts — and what will it cost?**

A deprecation notice, a new model release, a price change: something forces you
to consider swapping the LLM under a working product, and the honest answer is
usually "we'll find out in production." agentrec turns that into a report. It
**replays your recorded API traffic against a candidate model**, translates
across providers where needed (OpenAI ↔ Anthropic), scores every response
against what the old model produced, and prices the difference — so the
model-swap decision comes with evidence instead of a shrug.

The dataset is the part you don't have to build. **Your recorded traffic is
your eval set:** agentrec records LLM calls at the httpx transport layer (below
the OpenAI SDK, the Anthropic SDK, LangChain, or any httpx-backed client), so
the prompts you already run in development or production *are* the corpus you
migrate against — no hand-authored test cases, no golden answers to maintain.

> **Status:** beta (0.8.0). Migration translation covers OpenAI ↔ Anthropic
> conversations including **tool use** (definitions, assistant tool calls, tool
> results) and JSON mode; a **Gemini** dialect is included as a third
> translation target (request/response, streaming and tool-call paths verified
> against the live API — see `tests/test_live_gemini.py`). Images and strict
> `json_schema` become clearly-reasoned skipped rows. Record/replay is proven for streaming (SSE) and non-streaming
> (JSON) on OpenAI and Anthropic, sync and async — or **import** an existing
> Langfuse / LangSmith / OpenTelemetry export as a corpus without running the
> recorder at all. The API may still change in minor releases before 1.0. See
> [CHANGELOG](CHANGELOG.md).

## The report is the product

Here is a real report: 100 recorded `gpt-4o-mini` prompts (classification,
JSON extraction, summarization, rewriting, translation) replayed against
`claude-haiku-4-5` and scored offline. The full rendered versions are in
[`docs/sample-report.html`](docs/sample-report.html) (self-contained, open it
in a browser) and [`docs/sample-report.md`](docs/sample-report.md); the head of
it:

> # Migration Report — gpt-4o-mini → claude-haiku-4-5
>
> `corpus` · target `claude-haiku-4-5` (anthropic) · comparators exact, fuzzy
>
> **100 compared** (100 cached, 0 live) · 0 skipped · 0 errored
>
> | Comparator | Passed | Pass rate | Mean score |
> |---|---:|---:|---:|
> | exact | 22/100 | 22% | 0.22 |
> | fuzzy | 48/100 | 48% | 0.65 |
>
> | Metric | Baseline | Target | Ratio |
> |---|---:|---:|---:|
> | Output tokens | 1,435 | 3,059 | 2.13× |
> | Est. cost (anthropic-list+openai-list) | $0.001658 | $0.020655 | 12.46× |
>
> ### By category — _pass rate · mean score; tokens & cost are target/baseline ratios_
>
> | Category | Prompts | exact | fuzzy | Out tokens | Cost |
> |---|---:|---:|---:|---:|---:|
> | classify | 30 | 7% · 0.07 | 13% · 0.25 | 9.40× | 25.16× |
> | extract | 30 | 57% · 0.57 | 93% · 0.95 | 1.42× | 9.69× |
> | rewrite | 15 | 13% · 0.13 | 40% · 0.72 | 1.65× | 10.45× |
> | summarize | 15 | 0% · 0.00 | 7% · 0.62 | 1.18× | 8.60× |
> | translate | 10 | 10% · 0.10 | 90% · 0.90 | 1.68× | 10.89× |

That table is the decision in one glance — and a real finding: extraction and
translation hold up, but on this corpus Haiku is markedly more *verbose*
(classification answers run 9× the tokens because it adds a preamble), which
both inflates cost and tanks `exact`/`fuzzy` matching for short-label tasks. A
report drills down per row, with the prompt, both responses, per-field diffs,
and per-row cost/latency. (`exact`/`fuzzy` are the offline comparators used
here; `judge` or `embedding` would score the verbose-but-correct classification
answers more fairly — see [Comparators](#comparators).)

## 30-second demo

Record once, migrate, gate — three commands. Recording happens through one
httpx client you hand to your SDK:

```python
import agentrec
from openai import AsyncOpenAI

store = agentrec.FileStore("corpus")
http = agentrec.async_client()          # honours the active cassette scope
oai = AsyncOpenAI(http_client=http)

@agentrec.cassette(store, mode="auto", metadata={"category": "classify"})
async def ask(prompt: str) -> str:
    r = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content
```

```bash
# 1. (your app runs; cassettes accumulate under corpus/)
# 2. replay the whole corpus against a candidate model and score it
agentrec migrate --corpus corpus --target claude-haiku-4-5 --compare "exact,fuzzy,judge"
# 3. gate it: fail CI if fewer than 90% of compared rows still pass
agentrec report --corpus corpus --target claude-haiku-4-5 --compare exact \
    --strict --min-pass exact=0.9
```

`agentrec report` is the offline path: it re-renders from cached answers and
verdicts without touching the network, so it's safe to run in CI. See
[`examples/`](examples/) for runnable scripts (a text-corpus migration, a
tool-calling agent step, and a CI workflow snippet).

## Two ways to use it

**Episodic — the migration event.** A model is deprecated, a cheaper one ships,
a price changes. Point the runner at your corpus and the new model and read the
report. This is the few-times-a-year use.

**Recurring — the regression gate.** Prompt edits and model bumps are weekly,
and either can silently change behaviour. Because every recording carries a
`semantic_key` (a hash of the provider-neutral conversation) that groups the
*same logical prompt* across model and parameter changes, you can keep a frozen
corpus as a behavioural baseline and gate every change in CI:

```bash
# in CI, on every PR that touches prompts or model config
agentrec report --corpus corpus --target $CANDIDATE_MODEL \
    --compare "exact,json:category,priority" \
    --strict --min-pass exact=1.0 --min-pass "json:category,priority"=0.95
```

A prompt edit that quietly regresses your classification labels, or a model bump
that changes structured-output shape, now fails the build with the offending
rows named — the same machinery as the migration report, run continuously.
This is what earns agentrec a permanent place in CI rather than a one-off look.

## Comparators

The runner re-asks every corpus prompt of the target, caches the answers back
into the corpus, and scores baseline vs. target with one or more comparators:

| Comparator  | Needs network? | What it measures                                   |
| ----------- | -------------- | -------------------------------------------------- |
| `exact`     | no             | normalized string equality (classification-style)  |
| `fuzzy`     | no             | `difflib` sequence similarity                      |
| `json`      | no             | structural field-by-field match of JSON payloads   |
| `toolcalls` | no             | which tools were called, with what arguments       |
| `embedding` | OpenAI API     | cosine similarity of embeddings                    |
| `judge`     | LLM API¹       | an LLM scores semantic equivalence                 |

¹ judge verdicts are cached into the corpus — only new (baseline, target) pairs
cost an API call, and `agentrec report` (offline) replays cached verdicts
without a socket.

The offline comparators (`exact`, `fuzzy`, `json`) tolerate a markdown code
fence wrapping the whole payload — a target that emits ```` ```json … ``` ````
isn't unfairly zeroed. For structured outputs (a JSON object with some fixed
fields and some free text), `json` scores the fraction of fields that match, so
a `category`/`priority` agreement with a differing `summary` scores high instead
of zero, and the per-field diff (`priority: high→medium`) lands in the report.

When the free text shouldn't count at all, **scope** the comparator:
`json:category,priority` scores and passes on just those fields (dotted paths
for nested objects — `meta.source` — and `[i]` for list indices — `labels[0]`;
an entry covers its subtree). Out-of-scope diffs still appear in the report,
marked informational. In a spec, tokens after `json:` that aren't comparator
names continue the scope, so `exact,fuzzy,json:category,priority` is three
comparators.

### Gating: `--strict` and `--min-pass`

`--strict` alone is all-or-nothing: any failed or errored comparison (or an
all-skipped run) exits 1. For corpora with free-text fields that's permanently
red, so gate on pass rates instead: `--strict --min-pass
"json:category,priority"=0.9` exits by whether ≥ 90 % of compared rows passed
that comparator — comparators without a threshold become informational
(`--min-pass` is repeatable; comparator errors and errored rows still fail the
gate). Thresholds and actual rates land in a "Strict gate" section of the
report. Re-runs are cheap: answered prompts and judge verdicts are served from
disk, rate-limited or header-bloated calls (429/431/5xx) retry with backoff,
and failures are never cached. Rows are scored concurrently (`--concurrency`).

### Tool calls

Tool-using recordings migrate too. Tool definitions, assistant tool calls and
tool results all have a provider-neutral form, so an agent step recorded against
OpenAI (`tools` + `tool_calls` + `role: "tool"` messages) re-asks cleanly of
Claude (`input_schema` + `tool_use` + `tool_result` blocks) and vice versa —
`tool_choice` translates as well (`required` ↔ `any`, forced tool ↔ forced
tool). The `toolcalls` comparator then scores **selection and arguments**: did
the target call the same tools, in the same order, with the same argument values
(field-by-field, like the `json` comparator)? Recorded tools are **never
executed** — the comparison is about what the model decided to do, not what the
tool would have returned. Two responses that both called no tools pass
trivially; "didn't reach for a tool" is behaviour worth confirming too. For
tool-calling rows the text comparators and the judge see the response's
canonical rendering (text plus one line per call), so an empty-text tool call
never trivially "matches".

```bash
agentrec migrate --corpus corpus --target claude-haiku-4-5 --compare "toolcalls,judge"
```

### Multi-turn conversations and agent transcripts: step-wise, by design

A recorded multi-turn conversation (or agent loop) replays against the target
as a **step-wise evaluation**: each recorded request carries the baseline's
history — including the baseline model's own earlier replies, tool calls and
tool results — and the target model is asked for *its next action given that
history*. That is deliberate. Re-driving the whole loop with the target would
need live tools and would diverge after the first differing step, telling you
nothing attributable; holding the history fixed isolates exactly one question
per row: *at this point in a real conversation, does the new model do what the
old one did?* Every recorded turn of an agent loop becomes its own row, so a
6-step agent trace yields 6 independently-scored decisions. What this
methodology does **not** measure is error recovery — how the target would handle
the conversation *its own* earlier answers would have produced.

## Estimated cost

**Cost is a derived metric.** Tokens are what the cassettes record; `--pricing
PROFILE` prices them at report time against versioned snapshots — dated,
immutable JSON files of per-model rates (per token category: input, cached
reads/writes, output). Built-in `anthropic-list` and `openai-list` profiles ship
with the package; point `--pricing-dir` at your own snapshots to add profiles
(OpenRouter, enterprise contracts) or shadow a built-in. `a+b` composes profiles
for cross-provider runs, `--pricing` is repeatable for side-by-side views, and
`--pricing-as-of latest|recorded|YYYY-MM-DD` picks whether to price at today's
rates, at each cassette's recording date, or pinned for reproducing a historical
report. Reports gain baseline→target cost totals, per-row/per-category columns,
and a provenance section naming every snapshot used (with its sha256). Estimates
missing a rate are flagged, never silently zero, and **cost never gates
`--strict`.**

```bash
agentrec report --corpus corpus --target claude-haiku-4-5 --compare json \
    --pricing "anthropic-list+openai-list" --pricing-as-of latest
```

### Latency

The transports stamp every cassette with `latency_s` (request sent → response
finished, plus `latency_first_chunk_s` for streams), and the migration runner
times its live target calls, so reports show a per-row `Latency` column, a
baseline→target mean with a ratio, and a per-category latency ratio. Read it as
an indication, not a benchmark: the baseline number is recording-time provenance
— whatever the network and provider load looked like when the cassette was
recorded. Latency never gates `--strict`.

## How the corpus is built: record / replay

agentrec records at the **httpx transport layer**, below any SDK. The core
depends on nothing but `httpx`. Building one client and handing it to your SDK
gives you the corpus the migration runner consumes — and, as a free side
benefit, deterministic offline replay (fast, network-free tests of the exact
recorded traffic).

```bash
pip install agentrec                 # core is httpx-only
pip install "agentrec[compression]"  # + brotli/zstd cassette decoding
```

`mode="auto"` (shown in the demo above) replays a request if it's been recorded,
otherwise records it. Streaming works identically — the raw SSE bytes are
recorded and the SDK parser re-runs on replay. `cassette` also works as an async
context manager, and the same client plugs into the Anthropic SDK unchanged:
`AsyncAnthropic(http_client=http)`. Synchronous SDKs use the same seam: build
`agentrec.sync_client()`, hand it to `OpenAI(http_client=...)` /
`Anthropic(http_client=...)`, and use `cassette` as a plain `with` block or
decorator.

Prefer wiring httpx yourself? Use the transports directly:

```python
from agentrec import RecordingTransport, ReplayTransport

httpx.AsyncClient(transport=RecordingTransport(httpx.AsyncHTTPTransport(), store))
httpx.AsyncClient(transport=ReplayTransport(store))   # offline; cannot touch the network
```

Recordings tagged with a category —
`cassette(store, metadata={"category": "extract"})` — get a per-category
breakdown in the report. `agentrec annotate --corpus corpus` backfills
summaries and metadata onto an existing corpus.

### Importing an existing observability export

Already shipping traffic to an LLM-observability backend? You don't need to run
the recorder at all. `agentrec import` reads a **Langfuse**, **LangSmith** or
**OpenTelemetry GenAI** export and writes cassettes the migration runner
consumes like recorded ones:

```bash
agentrec import --source langfuse --input traces.jsonl --corpus corpus
agentrec import --input otel-spans.json --corpus corpus   # --source auto-detected
```

An exported interaction has the prompt and the answer but not the original wire
bytes, so an imported cassette is **synthesized**: one non-streaming JSON
request/response in a canonical dialect, marked `imported_from` /
`imported: true` in its metadata (the real baseline model id is preserved, so
reports still name the model that answered). Because `semantic_key` is derived
from the provider-neutral conversation, imported and natively-recorded prompts
group together — so you can bring months of production traffic to a migration
with no code change, no perf hit, and no PII review of live recording. A record
an importer can't parse becomes a skipped entry with a reason, never a failed
run.

### Recording in production (and why you might not)

The natural next question is "should I just run the recorder in prod?" Usually
**no** — prefer the importer above: it needs no change in the hot path and no
new place for prompts to land on disk. If you *do* record live, treat the
corpus as sensitive:

- **Sample.** You want coverage of each prompt *shape*, not every call. Gate
  the `cassette` scope behind your own sampler and record a small fraction;
  `semantic_key` grouping means one good recording per shape is enough for a
  full migration corpus, so a low rate keeps both the corpus and the overhead
  small.
- **Scrub responses too.** `FileStore` redacts auth headers and scrubs known
  secret shapes from request bodies by default, but response bodies are stored
  verbatim (they are the replay source of truth). Pass
  `scrub_response_body=True` for live corpora, and extend `secret_patterns=[...]`
  with your organisation's token shapes.
- **Set a retention policy.** Cassettes are plain files — rotate and expire
  them like any other data export, and review a corpus before sharing it.

### Design notes

```
agentrec/
  capture.py      # storage-agnostic captured request/response data
  keying.py       # request fingerprint → provider / model / semantic_key / cassette id
  store.py        # InMemoryStore + FileStore (human-readable JSON cassettes)
  transport.py    # RecordingTransport / ReplayTransport / AutoTransport
  session.py      # async_client() + cassette — the ergonomic seam
  providers/      # OpenAI + Anthropic + Gemini request/response dialects
  comparators.py  # exact / fuzzy / json / toolcalls / embedding / judge scoring
  migration.py    # run_migration() — replay the corpus against a candidate model
  importers.py    # Langfuse / LangSmith / OTel exports → synthesized cassettes
  pricing.py      # versioned pricing snapshots → derived cost estimates
  pricing_data/   # built-in list-price snapshots (anthropic-list, openai-list)
  report.py       # Markdown / HTML / console rendering
  cli.py          # agentrec migrate | report | annotate | import
```

- **Tee, don't buffer:** the caller and the store see every chunk in order,
  live — the recorder never holds back the stream.
- **Raw bytes, no parsing:** cassettes store the original byte frames; the SDK
  parser re-runs on replay, so one codebase covers every provider.
- **Replay mode can't leak:** `ReplayTransport` (`mode="replay"`) has no inner
  transport, so it cannot accidentally hit the network — use it for a hard
  offline guarantee. `mode="auto"` *does* make a live call (and records it)
  whenever a request has no recording yet — e.g. after a prompt edit changes the
  fingerprint.
- **Failures aren't cached:** non-2xx responses are never recorded by default
  (`record_errors=True` opts in), so a transient 429/500 can't be replayed
  forever as the answer.
- **Two-level identity:** interactions replay by a request *fingerprint* (method
  + path + model + normalised body); the migration report groups prompts by
  *`semantic_key`* (the provider-neutral conversation), so the same prompt
  against OpenAI or Anthropic, at any temperature, groups together.
- **Best-effort secret hygiene:** `FileStore` always redacts auth headers and
  scrubs *known* secret shapes from request bodies and summaries before anything
  touches disk. This is a safety net, not a guarantee — response bodies are
  stored verbatim unless you opt in via `scrub_response_body=True`, and unknown
  secret formats pass through. Review cassettes before sharing a corpus; extend
  `secret_patterns=[...]` with your organisation's shapes.

Any SDK that accepts an httpx client works. Non-httpx SDKs (boto3/Bedrock, some
Vertex paths) never route through the transport, so they need a different seam.

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
