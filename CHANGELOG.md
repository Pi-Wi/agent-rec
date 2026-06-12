# Changelog

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
