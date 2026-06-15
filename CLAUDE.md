# agentrec — LLM contributor context

Read this before opening source files; it encodes the architecture, the
invariants, and the gotchas. Most tasks need only 1–3 source files once you
know where things live.

## What this is

Framework-agnostic **record/replay for LLM API traffic** (at the httpx
transport layer, below any SDK) plus a **model-migration report** built on the
recorded corpus: replay every recorded prompt against a target model,
translate cross-provider (OpenAI ↔ Anthropic ↔ Gemini), score baseline vs.
target with pluggable comparators, gate CI on pass rates, and derive
cost/latency columns. The corpus can also be **imported** from an
observability export (Langfuse/LangSmith/OTel) instead of recorded.
Core runtime dependency: `httpx` only. Python ≥ 3.10. Version lives in
`pyproject.toml`; keep `CHANGELOG.md` updated in the same style (## Dev
(x.y.z) / ### Added / ### Changed, bold lead-ins, *why* included).

## Module map (agentrec/)

| File | Owns | Key symbols |
|---|---|---|
| `capture.py` | storage-agnostic captured interaction | `CapturedInteraction`, `CapturedRequest`, `CapturedChunk` (raw bytes + `timestamp_offset`) |
| `keying.py` | request identity | `fingerprint(request)` → `Fingerprint(provider, model, semantic_key, cassette_id)`; `fingerprint_of(interaction)`; `default_key` |
| `store.py` | persistence | `InteractionStore` interface (`save/load/has/discard/ids` async + `*_sync` twins), `InMemoryStore`, `FileStore` (human-readable JSON cassettes, auth-header redaction, secret scrubbing, summary block first) |
| `transport.py` | record/replay seams | `RecordingTransport`, `ReplayTransport` (offline, no inner transport — *cannot* hit network), `AutoTransport` (replay if recorded else record) + `Sync*` twins; `key=` fixed-string or callable keyer; `extra_metadata=` hook |
| `session.py` | ergonomic facade | `async_client()` / `sync_client()` (hand to any SDK via `http_client=`), `cassette(store, mode=...)` decorator/context manager, `DynamicTransport` |
| `providers/base.py` | provider-neutral forms | `ProviderAdapter` ABC (`extract_conversation` / `build_request` / `decode_response` / `normalize_usage`), `Conversation`, `DecodedResponse`, `ToolCall`, `TokenUsage`, `UnsupportedRequestError`, `DecodeError`, `MissingAPIKeyError`, `format_conversation`, `render_response`, `sse_data_lines` |
| `providers/openai.py` | chat-completions dialect | tools/`tool_calls`/`role:"tool"`, SSE delta accumulation, o-series quirks (`max_completion_tokens`, no sampling params) |
| `providers/anthropic.py` | Messages dialect | `tool_use`/`tool_result` blocks, `input_json_delta` accumulation, JSON-mode emulation via system-prompt suffix, role-alternation merging, `max_tokens` required |
| `providers/gemini.py` | Gemini `generateContent` dialect | `contents`/`parts` (roles user/model), `systemInstruction`, `functionDeclarations`/`functionCall`/`functionResponse` (results linked by *name*), native JSON via `responseMimeType`, `usageMetadata`; core paths (non-stream/stream/tool-calls/usage) **live-verified** via `tests/test_live_gemini.py` (gemini-2.5-flash); tool-result/JSON-mode build still offline-only |
| `providers/__init__.py` | registry + interaction helpers | `register` (later registrations win → override built-ins), `adapter_for_provider/model/host`, `decode_interaction`, `conversation_of`, `usage_of`, `build_summary`, content-encoding decompression |
| `comparators.py` | response scoring | `exact`, `fuzzy`, `json` (field scope `json:a,b`), `toolcalls`, `embedding` (OpenAI API), `judge` (LLM, corpus-cached verdicts); `parse_compare_spec`, `build_comparators`, `OFFLINE_COMPARATOR_NAMES`, `JUDGE_PREFIX` |
| `migration.py` | the runner | `run_migration()`, `RowResult`, `MigrationReport` (`.aggregates/.gates/.strict_passed/.token_totals/.latency_stats/.by_category`), `LatencyStats`, `annotate_corpus`, `MIGRATION_PREFIX`, retry/backoff on 429/431/5xx/529 |
| `importers.py` | observability-export importers | `import_corpus()` (async), `ImportSummary`, Langfuse/LangSmith/OTel-GenAI parsers → **synthesized** OpenAI-dialect JSON cassettes (`IMPORT_PREFIX`, `imported_from`/`imported` metadata, honest per-record skips) |
| `pricing.py` | derived cost estimates | `PricingCatalog.load(*dirs)`, `price_report()`, versioned immutable snapshots (`Decimal` math, sha256 provenance, `--pricing-as-of latest|recorded|YYYY-MM-DD`), built-ins in `pricing_data/` |
| `report.py` | rendering | `render_markdown` / `render_html` (self-contained, no JS) / `render_console` (ASCII-safe) |
| `cli.py` | `agentrec migrate \| report \| annotate \| import` | `report` is the offline path (offline comparators + judge from cached verdicts only); `import` seeds a corpus from an observability export |

## Core invariants — do not break these

1. **Raw bytes, no parsing in transports.** Cassettes store original wire
   bytes (compressed, chunk-split as received); the SDK parser re-runs on
   replay. Corpus tooling decompresses via the recorded `Content-Encoding`
   and must join *all* chunks before SSE parsing (chunks split frames
   mid-JSON).
2. **Tee, don't buffer.** `_TeeStream` forwards each chunk to caller and
   store concurrently; `on_done()` fires exactly once (exhausted or
   abandoned) via the finally/`aclose` path.
3. **Failures are never cached** (non-2xx unrecorded unless
   `record_errors=True`); the migration runner additionally `discard`s a
   cassette recorded for a non-200 before retrying. Malformed judge replies
   are never cached.
4. **Two-level identity.** `cassette_id` = method+path+model+normalized body
   (minus `stream`/`stream_options`) → record/replay key, distinguishes
   sampling params. `semantic_key` = hash of the provider-neutral
   conversation (system + messages + tool definitions; provider-minted
   tool-call ids stripped; `tool_choice: auto` ≡ absent; sampling params and
   `response_format` excluded) → groups the same logical prompt across
   providers/models for the migration report. **Text-only conversations must
   keep producing byte-identical canons** — semantic-key changes invalidate
   existing corpora grouping and need a CHANGELOG caveat (see 0.3.0/0.4.0/0.6.0
   entries). Adapter-unsupported requests fall back to a generic body hash.
5. **Honest skips.** Anything not faithfully translatable raises
   `UnsupportedRequestError` → a *skipped row with a reason*, never a silent
   behavior change. Currently skipped: images/non-text blocks, strict
   `json_schema`, legacy OpenAI functions API, server-side Anthropic tools,
   `n>1`, unparseable recorded tool-argument JSON (Anthropic targets only).
6. **Comparators degrade, never crash the run** — exceptions become
   `ComparisonResult(error=True)` on that row.
7. **Derived metrics never gate.** Tokens are canonical/recorded; cost and
   latency are derived/informational. `--strict` gates only on comparator
   outcomes (all-or-nothing, or `--min-pass` rates). An all-skipped run is
   NOT a pass. Missing pricing rates are flagged, never $0.
8. **Shared `Conversation` objects are never mutated** by `build_request`
   (e.g. JSON-mode system suffix is composed into the body only). Exception:
   the migration runner intentionally sets `conversation.temperature = None`
   cross-provider (noted on the row).
9. **Judge verdict cache** keys on `(judge_model, rendered_baseline,
   rendered_target)` — `render_response` equals `.text` for text-only
   responses, so existing caches stay valid; don't change that rendering
   lightly. Judge/migration cassettes (`judge__*`, `migration__*`) are
   excluded from the baseline set.
10. **Provenance over recomputation.** `recorded_at`, `latency_s`,
    `latency_first_chunk_s`, pinned `semantic_key`, `migrated_from`,
    `category` live in cassette metadata; `annotate_corpus` backfills with
    `setdefault` (pinned values win).

## Tool calls (0.6.0)

Neutral forms: `Conversation.tools = [{"name","description","parameters"}]`;
`tool_choice = None|"auto"|"required"|"none"|{"name": str}`; assistant message
`{"role","content","tool_calls":[{"id","name","arguments"(dict)}]}`; result
`{"role":"tool","tool_call_id","content"}`. `DecodedResponse.tool_calls` is a
tuple of `ToolCall`. Arguments that don't parse as JSON stay raw strings
(compare fine; skip on Anthropic build). Anthropic build merges consecutive
same-role messages (tool results = user-role blocks; API requires strict
alternation) and collapses single-text-block messages back to plain strings
(wire-shape compat). Missing ids are synthesized FIFO so call/result linkage
holds. The `toolcalls` comparator pairs by position: name mismatch = 0, else
fraction of matching flattened argument fields; never executes tools; both
sides calling nothing = pass. Multi-turn/agent evaluation is **step-wise by
design**: baseline history held fixed, target asked for its next action — one
row per recorded turn (documented in README; keep that framing).

## Migration runner mechanics

Rows = semantic_key groups (newest recording wins). One shared
`AutoTransport`+client; per-row identity (migration cassette id + lineage
metadata) travels in a `contextvars.ContextVar` because rows run as
concurrent asyncio tasks (bounded by `concurrency`). Migration cassette id:
`migration__<baseline_id>__to__<sanitized_model>` — deterministic, so re-runs
are served from disk. Target latency measured around the successful attempt;
baseline latency read from cassette metadata. `offline=True` must never open
a socket.

## Tests

`pytest -q` from repo root (venv: `.venv\Scripts\python.exe -m pytest -q` on
Windows). `asyncio_mode = "auto"` — async tests need no decorator. The suite
is **offline by default**: canned SSE/JSON fixtures via `httpx.MockTransport`;
accidental network = test failure (raising transports). Live tests
(`test_live_record.py`) run only with `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`
(from project-root `.env`) and skip cleanly. Fixture style: build
`CapturedInteraction`s by hand (see `_interaction`/`_sse` helpers in
`test_providers.py`); migration tests use a synthetic OpenAI SSE baseline
migrated to a mock Anthropic target (`test_migration.py`). New features need
tests in the same style; deliberately-hostile cases (mid-JSON chunk splits,
fenced output, malformed verdicts) are the house specialty.

## Conventions & gotchas

- Comments/docstrings explain *why* and the API contract, not what the next
  line does; module docstrings carry the design rationale. Match that.
- `--compare` spec parsing: tokens after `json:` that aren't comparator names
  continue the scope (`exact,fuzzy,json:category,priority` = 3 comparators);
  canonical scoped name (`json:a,b`) is the `--min-pass` key. A new
  comparator name = one entry in `OFFLINE_COMPARATOR_NAMES` (if offline) +
  `ALL_COMPARATOR_NAMES` + a factory in `build_comparators` + exports.
- Offline comparators strip a single whole-payload markdown fence
  (` ```json … ``` `) before comparing; inner backticks are content.
- `_scalars_match`: bools compare by identity (True ≠ 1), strings
  whitespace/case-normalized, numbers by equality (1 == 1.0); empty
  dict/list use sentinel objects.
- Adding a provider = one module subclassing `ProviderAdapter` + one
  `register()` call (later registrations override built-ins by host/model
  match). Non-httpx SDKs (boto3/Bedrock) can't use the transport seam at all.
- New public symbols must be exported through `agentrec/__init__.py`
  (`__all__`) and usually `providers/__init__.py`.
- Renderers: HTML is single-file/no-JS; console output must stay ASCII-safe
  (Windows terminals); markdown cells escape `|` and newlines.
- OpenAI o-series (`o1/o3/o4`): no `max_tokens` (use `max_completion_tokens`),
  no sampling params. Anthropic: `max_tokens` required (default 4096),
  `anthropic-version: 2023-06-01`, auth via `x-api-key`.
- Recorded auth headers are redacted on disk — rebuilt requests take fresh
  keys from env (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) or raise
  `MissingAPIKeyError`.
- Pricing snapshots are immutable dated JSON; never mutate one — add a new
  date. Profile name collisions: user `--pricing-dir` shadows built-ins.

## Imported (synthesized) cassettes

`agentrec import` writes cassettes that were never recorded: one synthesized
non-streaming JSON request/response in the **OpenAI chat-completions dialect**
(the universal shape), regardless of the source model's real provider. The
true model id is kept on the body (reports name it); `metadata.provider` is
`openai` (the synthesized wire dialect) and `imported`/`imported_from` flag the
synthesis honestly. One uniform dialect is deliberate — `semantic_key` is
provider-neutral, so imported and natively-recorded prompts group together.
Imported ids (`imported__…`) are ordinary baselines (only `migration__`/`judge__`
are excluded). Adding a source = one parser in `importers.py` + a `SOURCES`
entry; parsers raise `_Skip(reason)` for a record they can't use (never fatal).

## Roadmap candidates (agreed direction, not yet built)

See `TODO.md` for the live roadmap. **Shipped** since this note was first
written: Gemini adapter (0.8.0 — core paths live-verified via
`tests/test_live_gemini.py`), observability-export importers (0.8.0), README
repositioning (0.6.0).
**Still open:** OpenRouter-fed pricing-snapshot refresh, latency for streamed
targets, configurable judge model, an embedding comparator that doesn't require
an OpenAI key, and the OpenAI Responses API (`/v1/responses`) dialect.
