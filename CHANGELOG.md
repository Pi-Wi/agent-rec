# Changelog

## 1.0.0 — 2026-06-25

### Added
- **Structured-output & tool-call fidelity — three knobs the runner used to drop
  silently now ride or skip honestly (TODO P3).** A recorded request's strict
  `response_format: {"type": "json_schema", ...}`, its `parallel_tool_calls`
  flag, and each function's `strict: true` are captured into the neutral
  `Conversation` and re-emitted when the target speaks them: **OpenAI→OpenAI no
  longer skips a strict-schema prompt**, and carries the verbatim schema,
  `parallel_tool_calls`, and per-tool `strict`. A target that can't enforce a
  requested schema (Anthropic, Gemini, Mistral) raises `UnsupportedRequestError`
  from `build_request` → an **honest skipped row** ("target cannot represent
  request: …") rather than a prompt nudge pretending to enforce a contract.
  `parallel_tool_calls` and `strict` aren't fatal cross-provider — they're
  dropped, but **noted on the row** (`parallel_tool_calls=… not carried to
  anthropic`; `function strict-schema enforcement dropped …`), alongside the
  existing temperature-drop note. *Why:* these were the P3 "silently dropped"
  fidelity gaps; the project's contract is that nothing changes a request's
  meaning without saying so. Two new `ProviderAdapter` capability predicates
  (`carries_parallel_tool_calls` / `carries_function_strict`, default `False`,
  `True` on `OpenAIAdapter`, back to `False` on `MistralAdapter`) let the runner
  decide what to note without hard-coding provider names.
- **Public API declared, deprecation policy written (TODO P0).**
  `agentrec.__all__` now also exports `DEFAULT_SECRET_PATTERNS` and
  `scrub_secrets` — previously reachable only via the `agentrec.store`
  submodule, despite the README telling users to extend
  `secret_patterns=[...]` with them. A new `DEPRECATIONS.md` defines the
  public surface (Python `__all__`, the 5 CLI subcommands and their flags,
  and the cassette on-disk JSON structure) and what SemVer means for it:
  additive changes are minor, removing/renaming any of those — or changing
  the `semantic_key` algorithm — is a 2.0 event. *Why:* every other 1.0
  blocker is mechanical; this is the promise users actually rely on once
  they pin a version. The README's "API may still change in minor releases
  before 1.0" sentence is retired in favor of a link to the new policy.
- **Cassette-format stability guarantee decided; the `semantic_key` algorithm
  is now versioned (TODO P0).** Closes the half of the deprecation policy that
  `DEPRECATIONS.md` had three times explicitly deferred — *how a `semantic_key`
  change is handled post-1.0*. The decision: the **running release's algorithm
  is the grouping authority** (the runner already recomputes each key from the
  request bytes; the pinned `semantic_key` is recording-time provenance), and
  that algorithm is **frozen across all of 1.x**, so every 1.x release groups a
  kept corpus identically. To make a future change *detectable rather than
  silent*, cassettes (recorded **and** imported) now stamp
  `semantic_key_version` — `agentrec.SEMANTIC_KEY_VERSION`, currently `1` — the
  algorithm that produced their key; and the migration runner emits a
  non-gating **report warning** (`MigrationReport.warnings`) when a corpus's
  stamped version differs from the running release's, regrouping under the
  running algorithm but never silently. A 2.0 algorithm change bumps the
  version and ships an explicit re-key step (`agentrec annotate`); the new
  "Semantic-key stability & the 2.0 migration path" section of `DEPRECATIONS.md`
  specifies all of it. *Why:* a corpus is a frozen behavioural baseline kept for
  CI — a post-1.0 regroup must be a deliberate, visible migration, not a quiet
  surprise on upgrade, and the version stamp is the one piece that can't be
  added retroactively (hence at 1.0). Additive and behavior-preserving:
  recompute-based grouping is unchanged, so existing corpora and the shipped
  sample report are byte-identical; `annotate` stamps the version only when it
  is truthful (the pinned key still matches the current recompute), leaving a
  legacy key from an older algorithm un-versioned rather than mislabeled.
- **`py.typed` marker shipped — the package now advertises its types (TODO
  P0).** agentrec is thoroughly typed (dataclasses, typed returns throughout)
  but carried no [PEP 561](https://peps.python.org/pep-0561/) marker, so a
  downstream `mypy`/`pyright` silently treated it as untyped and ignored every
  annotation. `agentrec/py.typed` now ships **in the wheel** — verified by
  building and inspecting it: hatchling's default package inclusion
  (`packages = ["agentrec"]`) carries the marker alongside the `pricing_data/`
  snapshots, so no `force-include`/build-config change was needed. *Why:* a
  typed library that doesn't advertise it gives consumers none of the benefit,
  and the marker is far cheaper to promise at 1.0 than to retrofit after users
  pin a version.

### Changed
- **Build-time skips are caught, not crashes.** The migration runner now turns
  an `UnsupportedRequestError` from `build_request` into a skipped row (it
  previously caught only `MissingAPIKeyError` there). This closes a latent gap:
  the already-documented "unparseable recorded tool-argument JSON, Anthropic/
  Gemini target" skip was raised at build time but never caught, so it would
  have propagated out of `run_migration` instead of skipping the one row.
- **`semantic_key` caveat — strict-`json_schema` baselines regroup once.** Such
  requests used to fail extraction (json_schema was rejected) and fell back to
  the generic body-hash key; now they extract into a proper conversation and key
  on it, so an OpenAI baseline recorded with `response_format: json_schema`
  lands in the **same** group as the equivalent plain-text prompt (the intended
  grouping). Only these requests change key — text-only and tool-call corpora
  are byte-for-byte unchanged. Carrying a tool's `strict` flag does **not**
  change any key: it rides inside the tool dict but is projected out of the
  semantic-key canon (verified by tests), as are `parallel_tool_calls` and
  `response_format` (a format choice was never the question being asked).
- **Anthropic `tool_choice: {"type": "none"}` verified live (TODO P3).** New
  `tests/test_live_anthropic.py` drives the Anthropic-target path against the
  real `/v1/messages` API and confirms `none` is accepted and suppresses tool
  calls — paired with a forced-call control on identical input, so the contrast
  (forced → a call, none → none) is the proof, not a single well-formed request.
  Live note recorded in the test: with its only tool suppressed, Haiku may
  return empty content (`stop_reason: end_turn`) — model disposition, decoded
  faithfully, not a bug — so the test asserts call suppression, not a non-empty
  answer. An offline round-trip test (`extract` ↔ `build`) covers the wire
  spelling without a key.

## Dev (0.10.0)

### Added
- **Second-opinion judge — two LLM judges, disagreement flagged.** The `judge`
  comparator now takes an optional second model (`--judge-model-2`, or
  `$AGENTREC_JUDGE_MODEL_2`): both judges score every row, each verdict cached
  on its own model, and the row passes only when *both* call the responses
  equivalent. A split decision fails the row and is flagged `[judges
  disagreed]` in the report — the gate-safe default for a corpus where a single
  judge shouldn't quietly decide a CI pass/fail. *Why:* on gate-critical corpora
  a lone LLM verdict is a single point of failure; a cheap second opinion
  surfaces the rows worth a human's eyes. The single-judge path is byte-for-byte
  unchanged (same result shape, same cache ids), so existing cached verdicts
  stay valid.
- **Configurable judge model from the environment.** The judge model resolves
  `--judge-model` → `$AGENTREC_JUDGE_MODEL_1` (with the unsuffixed
  `$AGENTREC_JUDGE_MODEL` accepted as an alias) → built-in default
  (`claude-opus-4-8`), so the judge can be pinned once in `.env` instead of on
  every command. Exposed as `agentrec.DEFAULT_JUDGE_MODEL`.

### Changed
- **Migration targets are now streamed.** The runner issues its target call as a
  streaming request (`build_request(..., stream=True)` — `stream: true` for the
  chat-completions/Anthropic dialects, the `streamGenerateContent?alt=sse`
  endpoint for Gemini) and times the **real** first chunk, so a streamed
  baseline's true time-to-first-chunk now compares against a real target TTFB
  instead of a target whose first-chunk time was indistinguishable from its
  total (TODO P2). Reports gain a `TTFB (mean)` totals row, a per-row `TTFB`
  entry in the details, and a console line — shown only for rows where *both*
  sides streamed. The response is re-decoded by its content type, so a target
  that ignores `stream` and answers with a JSON body still decodes correctly;
  the recorded migration cassette is the SSE stream (cached re-runs read its
  TTFB from metadata). `stream`/`stream_options` stay out of a request's
  cassette identity, so a prompt keys the same whether or not it was streamed.
- `ProviderAdapter.build_request` grew a `stream: bool = False` keyword (default
  off, so the judge/embedding/import callers are unchanged). `OpenAIAdapter`
  adds `stream_options: {"include_usage": true}` when streaming so the report's
  token columns stay populated for streamed targets; `MistralAdapter` overrides
  this (Mistral streams usage by default and rejects `stream_options`) — a
  fourth dialect hook (`_stream_body_fields`) alongside the existing three.

## Dev (0.9.0)

### Added
- **Mistral adapter — a fourth translation dialect.** `providers/mistral.py`
  adds Mistral (`api.mistral.ai/v1/chat/completions`) as a migration
  source/target, so OpenAI ↔ Anthropic ↔ Gemini ↔ Mistral now all interoperate.
  Mistral speaks the **same chat-completions dialect as OpenAI** (`messages`,
  `tools` / `tool_calls`, SSE `chat.completion.chunk` deltas,
  `prompt_tokens` / `completion_tokens` usage, native
  `response_format: {"type": "json_object"}`), so the adapter subclasses
  `OpenAIAdapter` and overrides only the three places Mistral genuinely
  differs: it forces a tool call with `"any"` (OpenAI's `"required"`; both map
  to the neutral `"required"`); it validates `tool_call_id` against
  `^[a-zA-Z0-9]{9}$`, so an id carried over from another provider (Anthropic
  `toolu_…`, OpenAI `call_…`) or synthesized for a hand-built conversation is
  remapped to a stable 9-character form (call and result kept on one id); and
  none of its models carry the o-series `max_completion_tokens` quirk (Magistral
  reasons but bills the same way). Decoding, usage normalisation and
  conversation extraction are inherited unchanged. The core paths —
  non-streaming and streaming (SSE) decoding, request building, usage
  normalisation and a forced tool call — are **verified against the live API**
  by `tests/test_live_mistral.py` (run against `mistral-small-latest`; skips
  without a key). *Why:* OpenAI ↔ Anthropic ↔ Gemini ↔ Mistral is the set teams
  actually weigh, and Mistral was the cheapest dialect to add faithfully because
  it reuses the chat-completions machinery the OpenAI adapter already
  live-tests. Like Gemini, Mistral's SDK does not route through httpx, so seed a
  corpus via `agentrec import` and/or use Mistral as a migration *target*.
  Registered by host `mistral` and the `mistral-` / `open-mistral-` /
  `open-mixtral-` / `codestral-` / `ministral-` / `pixtral-` / `magistral-` /
  `devstral-` model prefixes. Exported as `agentrec.providers.MistralAdapter`.
- **Built-in `mistral-list` pricing profile.** A dated snapshot
  (`pricing_data/mistral-list/2026-06-16.json`) of Mistral La Plateforme list
  prices, so `--pricing mistral-list` (or `--pricing openai-list+mistral-list`
  for a cross-provider view) fills the cost columns for Mistral targets instead
  of flagging them unpriced. Same discipline as the other snapshots: immutable,
  dated, source-cited, verify-before-billing.

### Changed
- `OpenAIAdapter` grew three small, overridable dialect hooks
  (`_extract_tool_choice`, `_is_reasoning_model`, `_wire_call_id`, plus the
  `_required_tool_choice` token) so the Mistral subclass expresses its deltas
  without forking the chat-completions decode/build code. The defaults are
  no-ops: OpenAI's extracted conversations and built requests are byte-for-byte
  unchanged, so existing cassettes, `semantic_key` grouping and record/replay
  are untouched.

## Dev (0.8.0)

### Added
- **`agentrec import` — corpus importers from observability exports.** A new
  `import` subcommand (and `agentrec.import_corpus`) reads **Langfuse**,
  **LangSmith** or **OpenTelemetry GenAI** exports
  (`--source langfuse|langsmith|otel|auto`; JSON, JSONL or OTLP
  `resourceSpans`) and writes cassettes the migration runner consumes exactly
  like recorded ones — so a team already shipping traffic to an observability
  backend can run a migration **without running the recorder in prod** (no
  code change, no perf hit, no PII review of live recording). *Why:* getting
  the corpus in is the adoption bottleneck, not the engine. An exported
  interaction carries the prompt and the answer but not the original wire
  bytes, so each becomes a **synthesized** cassette: one non-streaming JSON
  request/response in the OpenAI chat-completions dialect, flagged
  `imported: true` / `imported_from: <source>` in metadata (the real baseline
  model id is preserved, so reports still name the model that answered). One
  uniform dialect is deliberate — `semantic_key` is provider-neutral, so an
  imported prompt and the same prompt recorded natively against another
  provider group into one migration row. Best-effort and never fatal: a record
  an importer can't parse becomes a skipped entry with a reason in the returned
  `ImportSummary`, and non-text parts (images) are dropped from the synthesized
  prompt. Imported ids (`imported__…`) are ordinary baselines. New exports:
  `import_corpus`, `ImportSummary`, `ImportSourceError`, `IMPORT_PREFIX`.
- **Gemini adapter — a third translation dialect.** `providers/gemini.py`
  translates the `generateContent` REST shape both ways (`contents`/`parts`
  with `user`/`model` roles, `systemInstruction`, `functionDeclarations` /
  `functionCall` / `functionResponse` — tool results linked back to their call
  *by name*, native JSON via `generationConfig.responseMimeType`) and decodes
  its responses (one JSON document or an `alt=sse` stream). `usageMetadata`
  normalizes into the disjoint token buckets (`promptTokenCount` is
  cache-inclusive, `candidatesTokenCount` is output, `thoughtsTokenCount` is
  informational reasoning). Registered by model prefix `gemini-` and host
  `generativelanguage`, so OpenAI/Anthropic ↔ Gemini migrations run and
  imported Gemini traffic decodes; non-text parts and non-object tool-call
  arguments stay clearly-reasoned skips (same constraints as Anthropic). The
  core paths — non-streaming and streaming (SSE) decoding, request building,
  usage normalisation and tool calls — are **verified against the live API**
  by `tests/test_live_gemini.py` (run against `gemini-2.5-flash`; skips
  without a key); a couple of build-side translations (tool-result
  `functionResponse`, JSON mode) remain offline-tested only. The Gemini SDK
  does not route through httpx, so live *recording* is unavailable — seed a
  corpus via `agentrec import` and/or use Gemini as a migration *target*.
  Exported as `agentrec.providers.GeminiAdapter`.
- README: documented the **production-recording story** ("Recording in
  production (and why you might not)") and the new **import** path. The
  importer is named as the recommended way to seed a corpus; the live-recording
  guidance (sampling, `scrub_response_body=True`, `secret_patterns`, retention)
  is there for when you must record in prod anyway.

### Changed
- **Migration report cleaned up for readability.** The per-prompt `Prompt`
  preview (Results table and Details headers) now shows the *last user
  message* instead of the conversation rendering — corpora that share one
  system prompt previously collapsed every row to an identical `[system] …`
  prefix that truncated before any distinguishing content. The redundant
  header bullet list, `> Verdict` blockquote and standalone summary table are
  merged into **one `## Summary`** (a compact metadata line, the comparator
  verdict table, and a baseline→target totals table for tokens/latency/cost).
  The `## Details` section now renders **failing rows first** (then lowest
  mean score) and is **capped at 25 entries** by default — `--max-detail-rows
  N` raises or removes the cap (`0` = all), with the omitted rows noted. *Why:*
  a 100-row report was an unscannable wall of identical previews and
  triplicated summary numbers.
- **Tool calls render as structured data, not inlined text.** `RowResult`
  carries `baseline_tool_calls` / `target_tool_calls` (tuples of `ToolCall`),
  and the report shows each side's prose plus a dedicated **Tool calls** block
  (name + arguments) in the Details panes; tool-calling rows are flagged in the
  Results table. The `*_text` fields now hold the response's prose only.
  *Why:* tool calls were flattened into the prose as `[tool_call] …` lines and
  dumped into the same code block, with no signal in the Results table — you
  could not tell a tool-calling step from prose at a glance. Comparators and
  the judge are unaffected: they score the decoded responses directly, so
  scoring and judge-verdict caching are unchanged.
- **`_provider_from_host` now resolves through the adapter registry** instead
  of hard-coded openai/anthropic host substrings, so a newly registered
  adapter (Gemini, or a custom override) tags its recordings with the right
  provider name without editing `keying.py`. The match is by the same host
  substrings as before, so existing cassette ids and provider tags for OpenAI
  and Anthropic are unchanged — and `semantic_key` is untouched (the
  conversation canon did not change), so existing corpora keep their grouping.
- **Reports are written to a dedicated `reports/` directory by default**,
  instead of the current working directory. `agentrec migrate|report` gain
  `--out-dir DIR` (default `reports`, created if missing); `--out` still takes
  an explicit base path and overrides it. *Why:* a run dropped timestamped
  `migration-report__*.{md,html}` files loose in the repo root. This also fixes
  report filenames for target ids containing a dot (e.g. `gemini-2.5-flash`),
  which the previous `Path.with_suffix` handling truncated. The shipped
  `examples/` write their reports under `reports/` too.

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
