# agentrec

Framework-agnostic record/replay for LLM API interactions — plus a
**model-migration report** built on the recorded corpus.

Recording happens at the **httpx transport layer**, below the OpenAI SDK, the
Anthropic SDK, LangChain, or any other httpx-backed client. The core depends
on nothing but `httpx`.

> **Status:** beta (0.6.0). Record/replay is proven for streaming (SSE) and
> non-streaming (JSON) responses on OpenAI and Anthropic, sync and async; the
> API may still change in minor releases before 1.0. Migration translation
> covers OpenAI ↔ Anthropic conversations including **tool use** (definitions,
> assistant tool calls, tool results) and JSON mode — images and strict
> `json_schema` become clearly-reasoned skipped rows.
>
> **0.6.0 highlights:** tool-calling conversations migrate cross-provider and
> a new offline `toolcalls` comparator scores tool *selection + arguments*
> (recorded tools are never executed); response **latency** is recorded by the
> transports and reported baseline→target. Earlier: estimated-cost columns
> (`--pricing`) from versioned pricing snapshots, a field-scoped `json`
> comparator (`json:category,priority`), threshold-based CI gating
> (`--strict --min-pass`), and judge verdicts cached into the corpus. See
> [CHANGELOG](CHANGELOG.md).

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

| Comparator  | Needs network? | What it measures                                   |
| ----------- | -------------- | -------------------------------------------------- |
| `exact`     | no             | normalized string equality (classification-style)  |
| `fuzzy`     | no             | `difflib` sequence similarity                      |
| `json`      | no             | structural field-by-field match of JSON payloads   |
| `toolcalls` | no             | which tools were called, with what arguments       |
| `embedding` | OpenAI API     | cosine similarity of embeddings                    |
| `judge`     | LLM API¹       | an LLM scores semantic equivalence                 |

¹ judge verdicts are cached into the corpus — only new (baseline, target)
pairs cost an API call, and `agentrec report` (offline) replays cached
verdicts without a socket.

The offline comparators (`exact`, `fuzzy`, `json`) tolerate a markdown code
fence wrapping the whole payload — a target that emits ```` ```json … ``` ````
isn't unfairly zeroed. For structured outputs (a JSON object with some fixed
fields and some free text), `json` is the metric to reach for: it scores the
fraction of fields that match, so a `category`/`priority` agreement with a
differing `summary` scores high instead of zero, and the per-field diff
(`priority: high→medium`) lands in the report.

When the free text shouldn't count at all, **scope** the comparator:
`json:category,priority` scores and passes on just those fields (dotted paths
for nested objects — `meta.source` — and `[i]` for list indices —
`labels[0]`; an entry covers its subtree). Out-of-scope diffs still appear in
the report, marked informational. In a spec, tokens after `json:` that aren't
comparator names continue the scope, so `exact,fuzzy,json:category,priority`
is three comparators.

```bash
agentrec migrate  --corpus corpus --target claude-haiku-4-5 --compare "exact,judge,json:category,priority"
agentrec report   --corpus corpus --target claude-haiku-4-5 --compare json --strict   # offline; CI gate
agentrec annotate --corpus corpus                                      # backfill summaries/metadata
```

`--strict` alone is all-or-nothing: any failed or errored comparison (or an
all-skipped run) exits 1. For corpora with free-text fields that's permanently
red, so gate on pass rates instead: `--strict --min-pass
"json:category,priority"=0.9` exits by whether ≥ 90 % of compared rows passed
that comparator — comparators without a threshold become informational
(`--min-pass` is repeatable; comparator errors and errored rows still fail
the gate). Thresholds and actual rates land in a "Strict gate" section of the
report.

Re-runs are cheap: answered prompts and judge verdicts are served from disk,
rate-limited or header-bloated calls (429/431/5xx) retry with backoff, and
failures are never cached. Rows are scored concurrently (`--concurrency`).
Recordings tagged with a category —
`cassette(store, metadata={"category": "extract"})` — get a per-category
breakdown in the report, with output-token columns that surface
verbosity/cost differences between the models.

**Estimated cost is a derived metric.** Tokens are what the cassettes record;
`--pricing PROFILE` prices them at report time against versioned snapshots —
dated, immutable JSON files of per-model rates (per token category: input,
cached reads/writes, output). Built-in `anthropic-list` and `openai-list`
profiles ship with the package; point `--pricing-dir` at your own snapshots
to add profiles (OpenRouter, enterprise contracts) or shadow a built-in.
`a+b` composes profiles for cross-provider runs, `--pricing` is repeatable
for side-by-side views, and `--pricing-as-of latest|recorded|YYYY-MM-DD`
picks whether to price at today's rates, at each cassette's recording date,
or pinned for reproducing a historical report. Reports gain baseline→target
cost totals, per-row/per-category columns, and a provenance section naming
every snapshot used (with its sha256) — so the numbers stay reproducible
after prices change. Estimates missing a rate are flagged, never silently
zero, and cost never gates `--strict`.

```bash
agentrec report --corpus corpus --target claude-haiku-4-5 --compare json \
    --pricing "anthropic-list+openai-list" --pricing-as-of latest
```

**JSON mode translates, it doesn't skip.** A baseline recorded with OpenAI's
`response_format={"type": "json_object"}` migrates cleanly: re-emitted
natively for OpenAI targets, and emulated on Anthropic via a system-prompt
instruction (which also discourages the code fences). The strict `json_schema`
variant stays an honest skip — a prompt nudge can't enforce a schema.

### Tool calls

Tool-using recordings migrate too. Tool definitions, assistant tool calls and
tool results all have a provider-neutral form, so an agent step recorded
against OpenAI (`tools` + `tool_calls` + `role: "tool"` messages) re-asks
cleanly of Claude (`input_schema` + `tool_use` + `tool_result` blocks) and
vice versa — `tool_choice` translates as well (`required` ↔ `any`, forced
tool ↔ forced tool). The `toolcalls` comparator then scores **selection and
arguments**: did the target call the same tools, in the same order, with the
same argument values (field-by-field, like the `json` comparator)? Recorded
tools are **never executed** — the comparison is about what the model decided
to do, not what the tool would have returned. Two responses that both called
no tools pass trivially; "didn't reach for a tool" is behaviour worth
confirming too. For tool-calling rows the text comparators and the judge see
the response's canonical rendering (text plus one line per call), so an
empty-text tool call never trivially "matches".

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
nothing attributable; holding the history fixed isolates exactly one
question per row: *at this point in a real conversation, does the new model
do what the old one did?* Every recorded turn of an agent loop becomes its
own row, so a 6-step agent trace yields 6 independently-scored decisions.
What this methodology does **not** measure is error recovery — how the target
would handle the conversation *its own* earlier answers would have produced.

### Latency

The transports stamp every cassette with `latency_s` (request sent → response
finished, plus `latency_first_chunk_s` for streams), and the migration runner
times its live target calls, so reports show a per-row `Latency` column, a
baseline→target mean with a ratio, and a per-category latency ratio. Read it
as an indication, not a benchmark: the baseline number is recording-time
provenance — whatever the network and provider load looked like when the
cassette was recorded. Latency never gates `--strict`.

## How it works

```
agentrec/
  capture.py      # storage-agnostic captured request/response data
  keying.py       # request fingerprint → provider / model / semantic_key / cassette id
  store.py        # InMemoryStore + FileStore (human-readable JSON cassettes)
  transport.py    # RecordingTransport / ReplayTransport / AutoTransport
  session.py      # async_client() + cassette — the ergonomic seam
  providers/      # OpenAI + Anthropic request/response dialects
  comparators.py  # exact / fuzzy / json / toolcalls / embedding / judge scoring
  migration.py    # run_migration() — replay the corpus against a candidate model
  pricing.py      # versioned pricing snapshots → derived cost estimates
  pricing_data/   # built-in list-price snapshots (anthropic-list, openai-list)
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
  report is derived from the provider-neutral conversation instead (system +
  messages + tool definitions, with provider-minted tool-call ids normalised
  away) — same prompt against OpenAI or Anthropic, at any temperature, groups
  together.
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
