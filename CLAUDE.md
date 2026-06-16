# agentrec — LLM contributor context

Read before opening source files: the architecture, invariants, and gotchas.
Most tasks touch only 1–3 source files once you know where things live.

## What this is

Framework-agnostic **record/replay for LLM API traffic** at the httpx transport
layer (below any SDK), plus a **model-migration report** over the corpus: replay
each recorded prompt against a target model, translate cross-provider
(OpenAI ↔ Anthropic ↔ Gemini ↔ Mistral), score baseline vs. target with
pluggable comparators, gate CI on pass rates, derive cost/latency. The corpus
can instead be **imported** from an observability export (Langfuse/LangSmith/
OTel). Sole runtime dep: `httpx`. Python ≥ 3.10. Version in `pyproject.toml`;
keep `CHANGELOG.md` in style (`## Dev (x.y.z)` / `### Added` / `### Changed`,
bold lead-ins, *why* included).

## Module map (agentrec/)

| File | Owns | Key symbols |
|---|---|---|
| `capture.py` | captured interaction | `CapturedInteraction`, `CapturedRequest`, `CapturedChunk` (raw bytes + `timestamp_offset`) |
| `keying.py` | request identity | `fingerprint(request)` → `Fingerprint(provider, model, semantic_key, cassette_id)`; `fingerprint_of`; `default_key` |
| `store.py` | persistence | `InteractionStore` (`save/load/has/discard/ids` async + `*_sync` twins), `InMemoryStore`, `FileStore` (human-readable JSON, auth redaction, secret scrubbing, summary-first) |
| `transport.py` | record/replay seams | `RecordingTransport`, `ReplayTransport` (offline — *cannot* hit network), `AutoTransport` (replay-else-record) + `Sync*` twins; `key=` fixed/callable; `extra_metadata=` |
| `session.py` | ergonomic facade | `async_client()` / `sync_client()` (any SDK via `http_client=`), `cassette(store, mode=...)` decorator/CM, `DynamicTransport` |
| `providers/base.py` | provider-neutral forms | `ProviderAdapter` ABC (`extract_conversation` / `build_request` / `decode_response` / `normalize_usage`), `Conversation`, `DecodedResponse`, `ToolCall`, `TokenUsage`, `UnsupportedRequestError`, `DecodeError`, `MissingAPIKeyError`, `format_conversation`, `render_response`, `sse_data_lines` |
| `providers/openai.py` | chat-completions dialect | tools/`tool_calls`/`role:"tool"`, SSE delta accumulation, o-series quirks (`max_completion_tokens`, no sampling); dialect hooks `_required_tool_choice`/`_wire_call_id`/`_is_reasoning_model` for subclasses |
| `providers/anthropic.py` | Messages dialect | `tool_use`/`tool_result` blocks, `input_json_delta` accumulation, JSON-mode via system-prompt suffix, role-alternation merging, `max_tokens` required |
| `providers/gemini.py` | `generateContent` dialect | `contents`/`parts` (user/model), `systemInstruction`, `functionDeclarations`/`functionCall`/`functionResponse` (results linked *by name*), native JSON via `responseMimeType`, `usageMetadata`; core paths **live-verified** (`test_live_gemini.py`, gemini-2.5-flash); tool-result/JSON-mode build offline-only |
| `providers/mistral.py` | Mistral chat-completions | **subclasses `OpenAIAdapter`**; overrides only tool_choice spelling (`any`↔neutral `required`), 9-char `tool_call_id` remap (`_wire_call_id`), no-o-series check (`_is_reasoning_model`→`False`), and stream fields (`_stream_body_fields`→`stream` only, no `stream_options`); decode/usage/extract inherited; core paths **live-verified** (`test_live_mistral.py`) |
| `providers/__init__.py` | registry + interaction helpers | `register` (later wins → overrides built-ins), `adapter_for_provider/model/host`, `decode_interaction`, `conversation_of`, `usage_of`, `build_summary`, content-encoding decompression |
| `comparators.py` | response scoring | `exact`, `fuzzy`, `json` (scope `json:a,b`), `toolcalls`, `embedding` (OpenAI), `judge` (LLM, corpus-cached verdicts; configurable model + optional second judge with disagreement flag, `DEFAULT_JUDGE_MODEL`); `parse_compare_spec`, `build_comparators`, `OFFLINE_COMPARATOR_NAMES`, `JUDGE_PREFIX` |
| `migration.py` | the runner | `run_migration()` (target call is **streamed** for a real TTFB), `RowResult`, `MigrationReport` (`.aggregates/.gates/.strict_passed/.token_totals/.latency_stats/.by_category`), `LatencyStats` (totals + TTFB means), `annotate_corpus`, `MIGRATION_PREFIX`, retry/backoff on 429/431/5xx/529 |
| `importers.py` | observability importers | `import_corpus()` (async), `ImportSummary`, Langfuse/LangSmith/OTel-GenAI parsers → **synthesized** OpenAI-dialect cassettes (`IMPORT_PREFIX`, `imported_from`/`imported`, honest per-record skips) |
| `pricing.py` | derived cost | `PricingCatalog.load(*dirs)`, `price_report()`, immutable dated snapshots (`Decimal`, sha256 provenance, `--pricing-as-of latest|recorded|YYYY-MM-DD`), built-ins in `pricing_data/` |
| `report.py` | rendering | `render_markdown` / `render_html` (self-contained, no JS) / `render_console` (ASCII-safe) |
| `cli.py` | `agentrec migrate \| report \| annotate \| import` | `report` = offline path (offline comparators + cached judge verdicts); `import` seeds a corpus from an export |

## Core invariants — do not break these

1. **Raw bytes, no parsing in transports.** Cassettes store original wire bytes
   (compressed, chunk-split as received); the SDK parser re-runs on replay.
   Corpus tooling decompresses via recorded `Content-Encoding` and joins *all*
   chunks before SSE parsing (chunks split frames mid-JSON).
2. **Tee, don't buffer.** `_TeeStream` forwards each chunk to caller and store
   concurrently; `on_done()` fires exactly once (exhausted or abandoned) via the
   finally/`aclose` path.
3. **Failures are never cached** (non-2xx unrecorded unless `record_errors=True`);
   the runner additionally `discard`s a cassette recorded for a non-200 before
   retrying. Malformed judge replies are never cached.
4. **Two-level identity.** `cassette_id` = method+path+model+normalized body
   (minus `stream`/`stream_options`) → record/replay key, distinguishes sampling
   params. `semantic_key` = hash of the provider-neutral conversation (system +
   messages + tool definitions; provider-minted call ids stripped;
   `tool_choice: auto` ≡ absent; sampling params and `response_format` excluded)
   → groups one logical prompt across providers/models. **Text-only
   conversations must keep producing byte-identical canons** — semantic-key
   changes invalidate corpus grouping and need a CHANGELOG caveat (see
   0.3.0/0.4.0/0.6.0). Adapter-unsupported requests fall back to a generic body
   hash.
5. **Honest skips.** Anything not faithfully translatable raises
   `UnsupportedRequestError` → a *skipped row with a reason*, never a silent
   behavior change. Raised at **extract** (the runner already skipped these) or
   at **build** time (the runner catches it there too now, turning it into the
   same skipped row instead of crashing). Skipped today: images/non-text blocks,
   strict `json_schema` *on a target without native enforcement* (OpenAI→OpenAI
   carries it), legacy OpenAI functions API, server-side Anthropic tools, `n>1`,
   unparseable recorded tool-argument JSON (Anthropic/Gemini targets only).
   Soft-dropped-with-a-note (not skipped): `parallel_tool_calls` and per-tool
   `strict` when the target can't carry them (`carries_*` adapter predicates).
6. **Comparators degrade, never crash** — exceptions become
   `ComparisonResult(error=True)` on that row.
7. **Derived metrics never gate.** Tokens are canonical/recorded; cost and
   latency are derived/informational. `--strict` gates only on comparator
   outcomes (all-or-nothing, or `--min-pass` rates). An all-skipped run is NOT a
   pass. Missing pricing rates are flagged, never $0.
8. **Shared `Conversation` objects are never mutated** by `build_request`
   (JSON-mode suffix composed into the body only). Exception: the runner sets
   `conversation.temperature = None` cross-provider (noted on the row).
9. **Judge verdict cache** keys on `(judge_model, rendered_baseline,
   rendered_target)` — `render_response` equals `.text` for text-only responses,
   so existing caches stay valid; don't change that rendering lightly.
   `judge__*` / `migration__*` cassettes are excluded from the baseline set. A
   two-judge run caches each verdict under its own model id (so the single-judge
   id is unchanged); the row passes only if both judges agree on `equivalent`,
   and a split is `passed=False` flagged `[judges disagreed]` (gate-safe).
10. **Provenance over recomputation.** `recorded_at`, `latency_s`,
    `latency_first_chunk_s`, pinned `semantic_key`, `migrated_from`, `category`
    live in cassette metadata; `annotate_corpus` backfills with `setdefault`
    (pinned values win).

## Tool calls (0.6.0)

Neutral forms: `Conversation.tools = [{"name","description","parameters"}]`;
`tool_choice = None|"auto"|"required"|"none"|{"name": str}`; assistant message
`{"role","content","tool_calls":[{"id","name","arguments"(dict)}]}`; result
`{"role":"tool","tool_call_id","content"}`. `DecodedResponse.tool_calls` is a
tuple of `ToolCall`. Non-JSON arguments stay raw strings (compare fine; skip on
Anthropic/Gemini build). Anthropic build merges consecutive same-role messages
(tool results = user-role blocks; API needs strict alternation) and collapses
single-text-block messages to plain strings (wire compat). Missing ids
synthesized FIFO so call/result linkage holds (Mistral then remaps to its 9-char
form). `toolcalls` comparator pairs by position: name mismatch = 0, else
fraction of matching flattened argument fields; never executes tools; both sides
calling nothing = pass. Multi-turn/agent eval is **step-wise by design**:
baseline history fixed, target asked for its next action — one row per recorded
turn (keep that README framing).

## Migration runner mechanics

Rows = semantic_key groups (newest recording wins). One shared
`AutoTransport`+client; per-row identity (migration cassette id + lineage) rides
a `contextvars.ContextVar` because rows run as concurrent asyncio tasks (bounded
by `concurrency`). Migration cassette id
`migration__<baseline_id>__to__<sanitized_model>` is deterministic, so re-runs
serve from disk. The target call is **streamed** (`build_request(stream=True)`)
so its time-to-first-chunk is real and comparable; the response is re-decoded by
content type (a JSON answer to a `stream` request still decodes). Target
latency + TTFB measured around the successful attempt; baseline latency + TTFB
read from metadata; TTFB stats only count rows streamed on both sides.
`offline=True` must never open a socket.

## Tests

`pytest -q` from repo root (Windows venv: `.venv\Scripts\python.exe -m pytest
-q`). `asyncio_mode = "auto"` — async tests need no decorator. Suite is
**offline by default**: canned SSE/JSON via `httpx.MockTransport`; accidental
network = failure (raising transports). Live tests
(`test_live_{record,gemini,mistral}.py`) run when the matching key is in
project-root `.env` — **all four provider keys are present here, so a bare
`pytest` makes paid calls; `--ignore` the live files to stay offline**. Fixture
style: hand-built `CapturedInteraction`s (`_interaction`/`_sse` in
`test_providers.py`); migration tests use a synthetic OpenAI SSE baseline →
mock Anthropic target (`test_migration.py`). New features need same-style tests;
hostile cases (mid-JSON chunk splits, fenced output, malformed verdicts) are the
house specialty.

## Conventions & gotchas

- Comments/docstrings explain *why* and the API contract, not what the next line
  does; module docstrings carry design rationale. Match that.
- `--compare` parsing: tokens after `json:` that aren't comparator names extend
  the scope (`exact,fuzzy,json:category,priority` = 3 comparators); canonical
  scoped name (`json:a,b`) is the `--min-pass` key. A new comparator = entry in
  `OFFLINE_COMPARATOR_NAMES` (if offline) + `ALL_COMPARATOR_NAMES` + factory in
  `build_comparators` + exports.
- Offline comparators strip one whole-payload markdown fence (` ```json … ``` `)
  before comparing; inner backticks are content.
- `_scalars_match`: bools by identity (True ≠ 1), strings whitespace/case-
  normalized, numbers by equality (1 == 1.0); empty dict/list use sentinels.
- Adding a provider = one module subclassing `ProviderAdapter` + one `register()`
  (later registrations override by host/model). A *variant* of an existing
  dialect subclasses that adapter: `MistralAdapter(OpenAIAdapter)` overrides only
  four hooks (`_required_tool_choice`/`_wire_call_id`/`_is_reasoning_model` are
  no-ops on OpenAI; `_stream_body_fields` is the one with a real OpenAI default —
  it carries `stream_options: {include_usage}`, which Mistral drops), keeping
  shared SSE/decode/extract in one place. Non-httpx SDKs (boto3/Bedrock, and the
  Gemini/Mistral SDKs) can't use the transport seam — import or use-as-target
  instead.
- New public symbols export through `agentrec/__init__.py` (`__all__`) and
  usually `providers/__init__.py` (adapter classes live at
  `agentrec.providers.X`, not top-level).
- Renderers: HTML single-file/no-JS; console ASCII-safe (Windows); markdown
  cells escape `|` and newlines.
- OpenAI o-series (`o1/o3/o4`): no `max_tokens` (use `max_completion_tokens`), no
  sampling. Anthropic: `max_tokens` required (default 4096),
  `anthropic-version: 2023-06-01`, `x-api-key`. Mistral: `Authorization: Bearer`,
  forces tools with `"any"`, `tool_call_id` must be `^[a-zA-Z0-9]{9}$`.
- Recorded auth headers are redacted on disk — rebuilt requests take fresh keys
  from env (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`GEMINI_API_KEY`/`MISTRAL_API_KEY`)
  or raise `MissingAPIKeyError`.
- Pricing snapshots are immutable dated JSON; never mutate — add a new date. User
  `--pricing-dir` shadows a built-in profile of the same name.

## Imported (synthesized) cassettes

`agentrec import` writes cassettes never recorded: one synthesized non-streaming
JSON request/response in the **OpenAI chat-completions dialect** regardless of
source provider. The true model id stays on the body (reports name it);
`metadata.provider` is `openai` and `imported`/`imported_from` flag the synthesis
honestly. One uniform dialect is deliberate — `semantic_key` is provider-neutral,
so imported and natively-recorded prompts group together. Imported ids
(`imported__…`) are ordinary baselines (only `migration__`/`judge__` are
excluded). Adding a source = one parser in `importers.py` + a `SOURCES` entry;
parsers raise `_Skip(reason)` (never fatal).

## Roadmap

See `TODO.md` for the live roadmap. **Shipped:** structured-output & tool-call
fidelity — strict `json_schema` (carried OpenAI→OpenAI, honest-skip elsewhere),
`parallel_tool_calls` and function `strict` (carried or dropped-with-a-note)
(0.11.0); streamed-target latency + TTFB and a configurable / second-opinion
judge (0.10.0), Mistral adapter + `mistral-list` pricing (0.9.0, live-verified),
Gemini adapter + importers (0.8.0), README repositioning (0.6.0). **Still open:**
OpenAI Responses API (`/v1/responses`) dialect, images/multimodal, project
hygiene (CONTRIBUTING, CI Windows runner).
