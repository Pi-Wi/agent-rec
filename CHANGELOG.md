# Changelog

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
