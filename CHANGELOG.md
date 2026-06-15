# Changelog

## Dev (0.6.1)

_Version bump to open the 0.6.1 development line; no functional changes yet._

## Dev (0.6.0)

### Added
- **Tool-use conversations migrate.** Tool definitions, assistant tool calls
  and tool results now have provider-neutral forms (`Conversation.tools` /
  `tool_choice`, `tool_calls` on assistant messages, `role: "tool"` result
  messages; `ToolCall` on `DecodedResponse`), translated in both directions
  between the OpenAI dialect (`tools` array / `tool_calls` / `role: "tool"`)
  and the Anthropic dialect (`input_schema` / `tool_use` / `tool_result`
  blocks, with role-alternation merging).  `tool_choice` maps across
  (`required` ↔ `any`, forced tool ↔ forced tool); the legacy OpenAI
  *functions* API, server-side Anthropic tools and unparseable recorded
  argument JSON stay clearly-reasoned skips.  Streaming decodes accumulate
  OpenAI `tool_calls` deltas and Anthropic `input_json_delta` fragments, so
  SSE-recorded agent steps decode like JSON ones.
- **`toolcalls` comparator** (offline): pairs baseline/target tool calls by
  position; a pair scores 0 on a name mismatch, else the fraction of matching
  argument fields (same flattening as `json`); missing/extra calls score 0,
  and two responses that both called no tools pass.  Recorded tools are
  **never executed** — the comparator scores what the model decided to do.
  Included in `--compare all` and the offline `report` set.  For tool-calling
  rows, `exact`/`fuzzy`/`embedding`/`judge` (and report panes/summaries) use
  the response's canonical rendering — text plus one deterministic
  `[tool_call] name({...})` line per call — so empty-text tool calls never
  trivially match; text-only responses render as their text exactly, keeping
  existing judge-verdict cache keys valid.
- **Latency capture and report columns.**  Recording transports stamp
  `latency_s` (request sent → response stream finished) and
  `latency_first_chunk_s` onto every cassette's metadata; the migration
  runner times live target calls and reads cached ones, populating
  `RowResult.baseline_latency_s` / `target_latency_s`.  Reports gain a
  per-row `Latency` column, a baseline→target mean + ratio summary line
  (`MigrationReport.latency_stats()` / `LatencyStats`), and a per-category
  latency ratio.  Informational only — latency never gates `--strict`, and
  the renderers carry the caveat that baseline latencies are recording-time
  provenance.
- README: documented the step-wise multi-turn methodology explicitly — each
  recorded turn replays with the baseline's history held fixed, isolating
  "does the new model take the same next action?" per row (and what that
  deliberately does not measure: error recovery on the target's own
  trajectory).

### Changed
- `semantic_key` of corpora recorded **with** tools: such requests previously
  fell back to the generic body hash (extraction raised); they now key via
  the provider-neutral conversation hash including tool definitions, with
  provider-minted call ids normalised away — the same agent step recorded on
  OpenAI and Anthropic now groups together.  Their keys differ from 0.5 —
  same caveat as the 0.3.0 semantic-key change (pinned keys on existing
  migration cassettes are kept; cassette ids and record/replay are
  unaffected).  Text-only conversations produce byte-identical canons and
  keep their 0.5 keys.
- Cassette summary blocks render tool calls in the `response` field, so a
  tool-calling cassette opens with what the model decided to do.
- **README repositioned around migration/regression testing.** Leads with the
  decision the tool supports ("will the new model break my prompts, and what
  will it cost?") and the zero-authoring insight ("your recorded traffic is
  your eval set"); a real 100-prompt sample report now sits above the fold
  (committed to `docs/sample-report.{md,html}`), the episodic-vs-recurring
  (CI gate) framing is explicit, and record/replay is demoted to a "how the
  corpus is built" section.  *Why:* the report is the product, and a repo
  visitor never saw one.
- **Curated `examples/` now shipped** (was gitignored): a text-corpus
  migration, a tool-calling agent step (`toolcalls` comparator), and a
  copy-paste CI regression-gate workflow (`--strict --min-pass`), with an
  `examples/README.md` index.

## Dev (0.5.1)

### Added
- **Estimated-cost columns in the migration report** (`--pricing PROFILE`).
  Tokens stay the canonical recorded metric — cassettes are untouched — and
  cost is *derived at report time* from versioned pricing snapshots: dated,
  immutable JSON files of per-model, per-category rates (`Decimal` math, no
  float drift). Built-in `anthropic-list` and `openai-list` profiles ship as
  package data; `--pricing-dir` merges your own (a profile named like a
  built-in replaces it, so a company can pin its own rates). `a+b` composes
  profiles for cross-provider migrations
  (`--pricing anthropic-list+openai-list`), and `--pricing` is repeatable for
  side-by-side cost views (list price vs. enterprise contract).
  `--pricing-as-of` picks the snapshot date policy: `latest` (default — both
  models priced on one consistent date, the forward-looking migration
  question), `recorded` (each row at its cassette's `recorded_at` — historical
  accuracy across price changes), or a pinned `YYYY-MM-DD`. Reports gain
  baseline→target cost totals and ratios, per-row and per-category cost
  columns, and a provenance section naming each snapshot used with its sha256
  — re-rendering a historical report is reproducible even after prices move.
  An estimate whose token categories have no rate is marked incomplete (`*`)
  rather than silently free; totals only sum rows where both sides priced
  completely; a model with no rate yields no estimate, never $0. Cost never
  gates `--strict`. API: `PricingCatalog` / `price_report()` /
  `TokenUsage`-typed `RowResult.baseline_usage` / `target_usage`, and
  renderers accept `pricing=[...]`.
- **Per-category token normalization** (`TokenUsage`): provider adapters now
  decode usage into disjoint buckets — `input` (uncached), `cache_read`,
  `cache_write`, `output`, plus informational `reasoning` — reconciling the
  providers' conventions (OpenAI nests cached/reasoning inside its totals;
  Anthropic keeps cache traffic additive). The verbatim usage dict is kept on
  `TokenUsage.raw`, and the raw bytes remain in the cassette, so better
  normalization can always be applied retroactively. Exported as
  `agentrec.TokenUsage` / `usage_of()`.

### Changed
- `RowResult.baseline_in_tokens` / `target_in_tokens` now count the *whole*
  prompt side (uncached + cache reads + cache writes). For Anthropic
  recordings with prompt caching, cache traffic previously wasn't counted;
  OpenAI recordings are unchanged.

## Dev (0.5.0)

### Added
- **Field-scoped `json` comparator**: `--compare "json:category,priority"`
  restricts which fields drive the score and the pass/fail verdict, so a
  free-text field (`summary`) no longer dilutes the signal of the fixed
  fields. Scope entries use the flattened-path syntax (dotted for nested
  objects — `meta.source` — and `[i]` for list indices — `labels[0]`); an
  entry covers its whole subtree. Out-of-scope differences are still shown in
  `detail`, marked informational. A scope matching nothing in either payload
  is a comparator error (it's almost certainly a typo — silent green would be
  worse). In a `--compare` spec, tokens after `json:` that are not comparator
  names continue the scope, so `exact,fuzzy,json:category,priority` is three
  comparators; a scoped and an unscoped `json` may coexist. The canonical
  spelling (`json:category,priority`) is the comparator's display name and
  the key `--min-pass` matches against. (Limitation: a JSON field literally
  named like a comparator — `fuzzy` — can't be scoped.) The spec parser is
  exported as `parse_compare_spec`.
- **Threshold-based `--strict` gating**: `--min-pass COMPARATOR=RATE`
  (repeatable, e.g. `--min-pass "json:category,priority"=0.9`) gates the
  `--strict` exit code on the named comparators' pass rates over compared
  rows; comparators without a threshold become informational. `--strict`
  without `--min-pass` keeps the all-or-nothing behaviour. An all-skipped run
  is still not a pass, and errored rows or comparator errors still fail the
  gate. Thresholds and actual rates are surfaced in the console output and as
  a "Strict gate" section in the Markdown/HTML reports
  (`MigrationReport.gates()` / `strict_passed` / `GateResult` in the API).
- **Judge verdicts are cached in the corpus**: with a store supplied (the CLI
  always passes its corpus), each judge verdict is persisted as a
  `judge__<model>__<hash>` cassette keyed on
  `(judge_model, baseline_text, target_text)` — same full-interaction shape
  as a `migration__` cassette — so re-rendering a report on unchanged texts
  replays verdicts instead of re-buying them. `agentrec report` (offline) now
  accepts `judge`: cached verdicts replay without a socket, rows without one
  degrade to errored comparisons. Judge cassettes are excluded from the
  baseline set, like migration cassettes. A malformed judge reply is never
  cached; an unreadable cached verdict is discarded and re-asked live.
- `JsonComparator` is now exported from the package root (it was missing).

### Changed
- **Judge boolean-vs-score inconsistencies are flagged**: `passed` still
  follows the judge's `equivalent` boolean, but when the numeric score
  disagrees (score ≥ 0.8 with `equivalent=false`, or score < 0.5 with
  `equivalent=true`) the inconsistency is appended to `detail` so report
  readers see it.

## Dev (0.4.0)

### Added
- **`json` comparator** (offline): parses baseline and target (after fence
  stripping), flattens them to scalar fields, and scores the fraction that
  match — so a structured output whose fixed fields agree but whose free-text
  field differs scores high instead of zero. `passed` requires every scalar
  field to match; the per-field diff (e.g. `priority: high→medium`) lands in
  `detail`. An unparseable baseline is a comparator error; an unparseable
  target is a failed comparison. Available everywhere `--compare` is
  (including the offline `report` command).
- **`response_format` translation**: OpenAI `{"type": "json_object"}` is no
  longer an unsupported request. It is captured as the provider-neutral
  `Conversation.response_format`, re-emitted natively for OpenAI targets, and
  emulated on Anthropic targets via a system-prompt suffix ("Respond with
  only a single JSON object. No prose, no markdown code fences."). The
  `json_schema` variant stays unsupported: strict structured output cannot be
  faithfully emulated by a prompt nudge.

### Changed
- **`exact`/`fuzzy` are fence-tolerant**: a single markdown code fence
  wrapping the *whole* payload (```` ```json … ``` ````) is stripped before
  normalization, so a target model that fences its structured output is no
  longer unfairly zeroed. Inner backticks and partial fences are untouched.
- `semantic_key` of corpora recorded **with** `response_format`: such
  requests previously fell back to the generic body hash (extraction
  raised); they now key via the provider-neutral conversation hash, so the
  same prompt with and without JSON mode groups together. Their keys differ
  from 0.3 — same caveat as the 0.3.0 semantic-key change (pinned keys on
  existing migration cassettes are kept; cassette ids and record/replay are
  unaffected).

### Fixed
- **HTTP 431 is retried** like other transient statuses: the runner builds
  fresh, minimal headers per row, so "Request Header Fields Too Large" is
  infrastructure noise, not a request defect — previously those rows errored
  out on the first report.

## Dev (0.3.0)

### Added
- **Sync support**: `sync_client()` plus `SyncRecordingTransport` /
  `SyncReplayTransport` / `SyncAutoTransport` for SDKs built on
  `httpx.Client`; `cassette` now works as a plain `with` block and decorates
  sync functions. Stores expose a `*_sync` interface (both built-ins are
  natively synchronous).
- `record_errors=` on the recording transports and `cassette`: non-2xx
  responses are **no longer recorded by default** — a cached failure could be
  replayed forever in auto mode. Opt in to capture them deliberately.
- `scrub_response_body=True` on `FileStore` for opt-in best-effort scrubbing
  of response chunks (off by default: chunks are the replay source of truth).
- More built-in secret patterns (GitHub/Google/Slack tokens, JWTs, PEM
  private keys, URL credentials).
- Provider registry: `register` and the `adapter_for_*` lookups are exported
  at the top level, and **later registrations win**, so a custom adapter can
  override a built-in.
- Migration report rows are flagged when the target response was truncated by
  its token cap (the verbosity/token-ratio signal is skewed on such rows).
- `Retry-After` HTTP-date form is now honoured (previously only
  delta-seconds).

### Changed
- **`semantic_key` is now prompt-level and provider-neutral**: it hashes the
  conversation extracted by the provider adapter (system + messages), so the
  same prompt recorded against OpenAI and Anthropic — or with different
  sampling parameters — groups together in the migration report. Requests no
  adapter understands fall back to a body hash without model/sampling
  fields. Cassette ids (record/replay keys) are unchanged; **semantic keys
  recomputed by the tooling differ from 0.2** (run `agentrec annotate` only
  on fresh corpora; pinned keys on existing migration cassettes are kept).
- `--strict` now fails when **nothing was compared**: an all-skipped run no
  longer green-lights a CI gate, and the CLI warns when 0 prompts ran.
- `FileStore` filenames: ids needing sanitization get a short digest suffix
  so distinct ids ("a/b" vs "a_b") can no longer collide on one file.
- OpenAI adapter: o-series targets get `max_completion_tokens` and no
  `temperature` (they reject both `max_tokens` and sampling params).
- Docs now state the secret-scrubbing scope honestly (best-effort, request
  side by default) and scope the "replay can't leak" guarantee to
  `mode="replay"`.

### Fixed
- SSE decoding strips exactly one leading space after `data:` per the spec
  (was `lstrip()`, which could eat significant payload whitespace) and
  handles bare `data` lines.
- The judge comparator now prefers the JSON object containing an
  `equivalent` key instead of blindly taking the first `{...}` in the reply.
- `_TeeStream` no longer double-closes the underlying network stream.

## 0.2.0 — 2026-06-11

First public (PyPI) release.

### Added
- **Model-migration report**: `agentrec migrate | report | annotate` CLI.
  Replays every corpus prompt against a target model (cross-provider
  OpenAI ↔ Anthropic translation included), caches target answers as
  `migration__…` cassettes, and renders Markdown/HTML/console reports.
- Comparators: `exact`, `fuzzy` (offline), `embedding`, `judge` (live), all
  scored side-by-side in one run.
- **Per-category breakdown**: recordings tagged via
  `cassette(store, metadata={"category": "..."})` are grouped per task type
  in the report.
- **Output-token columns** per row, per category, and report-wide
  (baseline vs target volume and ratio) as a verbosity/cost signal.
- **Concurrent row scoring** in `run_migration` (`concurrency`, default 8),
  with deterministic report order and a `progress` callback.
- **Retry with backoff** on rate-limited/overloaded target calls
  (429/500/502/503/529), honouring `Retry-After`; failed responses are never
  cached.
- `agentrec[compression]` extra for brotli/zstd cassette decoding.

### Fixed
- Corpus tooling (migration, summaries) now decompresses recorded responses
  per their `Content-Encoding` (gzip/deflate built in, brotli/zstd via the
  extra). Replay was always correct; decoding raw chunks was not.

## 0.1.0

Internal prototype: record/replay at the httpx transport layer (streaming SSE
and non-streaming JSON), `InMemoryStore`/`FileStore` with header redaction and
request-body secret scrubbing, request-fingerprint keying with
provider/model/semantic-key provenance, `async_client()` + `cassette` facade.
