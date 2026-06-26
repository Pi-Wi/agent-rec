# agentrec

**Will the new model break your prompts — and what will it cost?**

agentrec replays your **recorded LLM API traffic** against a candidate model,
scores each response against what the old model produced, and prices the
difference — so a model swap ships with evidence instead of a shrug.

The dataset is the part you don't build. agentrec records at the httpx transport
layer (below the OpenAI/Anthropic SDKs, LangChain, any httpx client), so the
prompts you already run *are* your eval set — no hand-written test cases, no
golden answers to maintain.

- **Translates across providers** — OpenAI ↔ Anthropic ↔ Gemini ↔ Mistral, including tool use and JSON mode.
- **Scores offline or with a judge** — `exact` / `fuzzy` / `json` / `toolcalls` / `embedding` / `judge`.
- **Prices and times the swap** — token, cost, and latency deltas, baseline → target.
- **Gates CI** — fail the build when too few rows still pass.
- **Or skip recording entirely** — import a Langfuse / LangSmith / OpenTelemetry export as a corpus.

> **Status:** stable (1.0.0), SemVer. The public API, CLI flags, and cassette
> format are covered — see [DEPRECATIONS](DEPRECATIONS.md) and
> [CHANGELOG](CHANGELOG.md). Images/multimodal are an honest skip for now.

## The report is the product

100 recorded `gpt-4o-mini` prompts replayed against `claude-haiku-4-5`, scored
offline ([full report](docs/sample-report.md) · [HTML](docs/sample-report.html)):

> **Migration Report — gpt-4o-mini → claude-haiku-4-5**
> 100 compared · 0 skipped · 0 errored
>
> | Comparator | Passed | Pass rate |
> |---|---:|---:|
> | exact | 22/100 | 22% |
> | fuzzy | 48/100 | 48% |
>
> | Metric | Baseline | Target | Ratio |
> |---|---:|---:|---:|
> | Output tokens | 1,435 | 3,059 | 2.13× |
> | Est. cost | $0.001658 | $0.020655 | 12.46× |

The finding in one glance: extraction and translation hold up, but Haiku is
markedly more *verbose* — classification answers run ~9× the tokens (it adds a
preamble), which inflates cost and tanks `exact`/`fuzzy` on short labels. The
full report drills into every row: prompt, both responses, per-field diffs, and
per-row cost and latency.

## Try it now — no keys, no cost

This repo ships the corpus behind that report — all 100 prompts *and* the
recorded answers — so a checkout renders a real report fully offline:

```bash
pip install -e .   # from a clone; the demo corpus/ ships in the repo, not the wheel
agentrec report --corpus corpus --target claude-haiku-4-5 --compare exact,fuzzy
```

Add `--pricing "anthropic-list+openai-list"` for cost columns, `--format html`
for a shareable file, or `agentrec profiles` to list the built-in pricing.

## Record → migrate → gate

Recording happens through one httpx client you hand to your SDK:

```python
import agentrec
from openai import AsyncOpenAI

store = agentrec.FileStore("corpus")
oai = AsyncOpenAI(http_client=agentrec.async_client())   # honours the active cassette scope

@agentrec.cassette(store, mode="auto", metadata={"category": "classify"})
async def ask(prompt: str) -> str:
    r = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content
```

```bash
# your app runs; cassettes accumulate under corpus/
agentrec migrate --corpus corpus --target claude-haiku-4-5 --compare "exact,fuzzy,judge"
agentrec report  --corpus corpus --target claude-haiku-4-5 --compare exact \
    --strict --min-pass exact=0.9     # offline, CI-safe; fails under 90%
```

`agentrec report` is the offline path — it re-renders from cached answers and
verdicts without touching the network. Runnable scripts (text corpus,
tool-calling agent, CI snippet) live in [`examples/`](examples/).

**Two ways to use it:**

- **Episodic** — a model is deprecated or a cheaper one ships: point the runner at your corpus and read the report.
- **Recurring** — every recording carries a `semantic_key` (a hash of the provider-neutral conversation) that groups the *same logical prompt* across model and parameter changes, so a frozen corpus becomes a behavioural baseline you gate every PR against.

## Comparators

The runner re-asks each prompt of the target, caches the answer, then scores
baseline vs. target:

| Comparator | Network? | Measures |
|---|---|---|
| `exact` | no | normalized string equality |
| `fuzzy` | no | `difflib` sequence similarity |
| `json` | no | field-by-field match of JSON payloads |
| `toolcalls` | no | which tools were called, with what arguments |
| `embedding` | OpenAI | cosine similarity of embeddings |
| `judge` | LLM | an LLM scores semantic equivalence |

- **Judge verdicts are cached** into the corpus, so only new pairs cost a call and `report` replays them offline. Configurable model (`--judge-model`); add `--judge-model-2` for a second opinion — both must agree or the row is flagged `[judges disagreed]`.
- **Scope `json`** to the fields that matter: `json:category,priority` passes on just those (dotted paths and `[i]` indices supported); out-of-scope diffs still show, marked informational.
- **Offline comparators tolerate a markdown fence** wrapping the whole payload, so a ```` ```json ```` target isn't unfairly zeroed.
- **Gate with `--strict`** (all-or-nothing) or `--strict --min-pass exact=0.9` (pass-rate thresholds, repeatable). Comparator and row errors always fail the gate; **derived cost and latency never do**.

## Tool calls, cost, latency

- **Tool calls migrate too.** Definitions, assistant calls, tool results, and `tool_choice` all have a provider-neutral form (OpenAI `tools`/`tool_calls`/`role:"tool"` ↔ Anthropic `tool_use`/`tool_result`). The `toolcalls` comparator scores selection and arguments; recorded tools are **never executed**. ([example](examples/tool_calling_migration.py))
- **Multi-turn is step-wise by design.** Each recorded turn replays with the baseline's history held fixed, and the target is asked for its next action — one independently-scored row per turn. This isolates *does the new model do what the old one did here?*; it deliberately does not re-drive the whole loop (that needs live tools and diverges after the first difference).
- **Cost is derived, never gating.** `--pricing PROFILE` prices recorded tokens against dated, immutable snapshots (`anthropic-list`, `openai-list`, `mistral-list` built in; `a+b` composes; `--pricing-as-of` pins the date). Missing rates are flagged, never $0.
- **Latency is an indication, not a benchmark.** Target calls are streamed for a real time-to-first-chunk; baseline numbers are recording-time provenance.

## How it works

- **Records at the httpx transport layer**, below any SDK — the core depends on nothing but `httpx`. `mode="auto"` replays a recorded request else records it; streaming and sync SDKs use the same seam (`agentrec.sync_client()`, or `RecordingTransport`/`ReplayTransport` directly).
- **Raw bytes, no parsing** — cassettes store the original wire frames and the SDK parser re-runs on replay, so one codebase covers every provider. `ReplayTransport` has no inner transport, so it physically can't reach the network.
- **Failures aren't cached** — non-2xx isn't recorded by default, so a transient 429 can't replay forever as the answer.
- **Import instead of recording** — `agentrec import --source langfuse|langsmith|otel --input … --corpus corpus` synthesizes cassettes from an export (the real model id is preserved); a record it can't parse is skipped with a reason, never a failed run.

```bash
pip install agentrec                 # core is httpx-only
pip install "agentrec[compression]"  # + brotli/zstd cassette decoding
```

**Recording live traffic? Treat the corpus as sensitive.** `FileStore` redacts
auth headers and scrubs known secret shapes from requests, but **response bodies
are stored verbatim** unless you pass `scrub_response_body=True`. Prefer the
importer (no hot-path change), sample by prompt *shape*, extend
`secret_patterns=[...]` with your token shapes, and review a corpus before
sharing it.

## Tests

```bash
pytest -q
```

Offline by default — canned fixtures, with accidental network access failing the
test. Live tests run only when provider keys are in a project-root `.env`, and
skip cleanly otherwise.

## License & attributions

See [LICENSE](LICENSE) and [NOTICE](NOTICE) (streaming capture/replay pattern
inspired by **baml_vcr**).
