# TODO — roadmap to a recommendable 1.0

Priorities from the 2026-06 product review. The engine is strong; what limits
the project is **how corpora get in** (funnel), **who can use it** (provider
coverage), and **how it presents itself** (positioning).

## Shipped

- **Positioning (0.6.0):** README repositioned around the migration decision
  ("will the new model break my prompts, and what will it cost?"), a real
  100-prompt sample report above the fold (`docs/sample-report.{md,html}`),
  episodic-vs-recurring (CI-gate) framing, curated `examples/` (text, tool-call,
  CI-gate workflow).
- **Funnel (0.8.0):** `agentrec import` for Langfuse/LangSmith/OTel-GenAI exports
  → synthesized cassettes (run a migration without recording in prod); the
  prod-recording story documented (and why you might not).
- **Provider coverage:** Gemini adapter (0.8.0) and Mistral adapter +
  `mistral-list` pricing (0.9.0), both with core paths live-verified. The triangle
  teams evaluate is now OpenAI ↔ Anthropic ↔ Gemini ↔ Mistral.
- **Engine (0.6.0):** tool-call translation (OpenAI ↔ Anthropic) + `toolcalls`
  comparator; latency capture + report columns; step-wise multi-turn methodology;
  CLAUDE.md contributor context.
- **Decision document (0.10.0):** the runner now **streams its target calls**, so
  a target's time-to-first-chunk is a real, comparable number — reports gain a
  TTFB baseline→target mean (and per-row line) over rows streamed on both sides,
  not an artifact of non-streaming calls. The `judge` comparator's model is
  configurable (`--judge-model` / `$AGENTREC_JUDGE_MODEL_1`, alias
  `$AGENTREC_JUDGE_MODEL`) and takes an optional **second opinion**
  (`--judge-model-2` / `$AGENTREC_JUDGE_MODEL_2`): both judges must agree for a
  row to pass, and disagreements are flagged for gate-critical corpora.
- **Structured-output & tool-call fidelity (0.11.0):** strict `json_schema`,
  `parallel_tool_calls` and function `strict: true` are no longer silently
  dropped. The neutral `Conversation` carries all three; OpenAI→OpenAI re-emits
  them faithfully (a strict-schema prompt no longer skips), a target without
  native schema enforcement raises a clean build-time skip, and the two
  non-fatal knobs are dropped *with a note on the row* cross-provider. The runner
  now catches `UnsupportedRequestError` at build time (closing a latent crash
  path for the unparseable-tool-args skip). Decided per P3: **carry
  same-dialect, note the drop otherwise** — never silent.

## P2 — importer & store hardening (funnel trust)

The funnel ("how corpora get in") is the #1 limiter, and an abuse pass (2026-06)
over the importer/store path surfaced trust gaps that are cheap to close. These
are small; bundle them as one release before the P3 capability work.

- [x] **Image-only turn → honest skip, not an empty prompt (2026-06).** A
  Langfuse/OTel turn whose only content was an image coerced to `""`, so the
  importer synthesized an empty-content request that 400s the target and
  *errors the row* — failing a `--strict` gate, a silent behavior change against
  invariant #5. The importer now skips it with a reason (`_has_usable_prompt`
  guard in `import_corpus`); a turn mixing text and an image keeps the text.
  This is **not** image support (P3) — just a guardrail so the funnel stays
  honest until multimodal lands.
- [x] **Honest store contract (2026-06).** `run_migration`/`annotate_corpus`
  enumerate the corpus via `store.ids()`, which was implemented **only on
  `FileStore`** — so `import_corpus()` into the public `InMemoryStore` then
  migrating raised `AttributeError`. `ids()` (sorted, sync) and `__len__` now
  live on the `InteractionStore` base (raising a clear error if a store leaves
  them unimplemented) and on `InMemoryStore`; a base `__bool__` keeps an empty
  store truthy so `if store:` presence checks (e.g. the judge cache) don't
  silently flip. CLAUDE.md's module-map line is corrected (`ids`/`__len__` are
  sync, not async twins). Unlocks fast in-memory migration tests
  (`tests/test_store.py` + an InMemoryStore end-to-end in `tests/test_import.py`).
- [ ] **Import → next-step hint.** A freshly imported corpus has baseline answers
  but no *target* answers yet, so `agentrec report` (offline) skips every row —
  the first thing a new user hits after `import`. Have `agentrec import` print
  the next step ("run `agentrec migrate --target …` to fill target answers;
  `report` is offline after that").
- [ ] **PII hygiene on the `import` CLI.** The importer is pitched as the
  PII-safer alternative to live recording, yet the CLI builds a *default*
  `FileStore` — scrubs known credential shapes only (an `sk-` key), never PII
  (email/SSN/phone) and never response bodies. Add `--scrub-response-body`,
  `--secret-patterns FILE`, a `--redact-pii` preset, and `--dry-run` (print the
  import summary without writing, to vet an export first). Ship PII patterns as
  documented best-effort (locale-specific, never complete), matching the
  existing `FileStore` honesty — not a compliance guarantee.
- [ ] **Importer robustness.** Auto-detect samples a *single* record
  (`_detect_source` → first dict wins), so a mixed or odd-first export
  mis-routes the whole file — vote across the first N. And let the import
  summary write to JSON (the CLI truncates skips at 10; large exports otherwise
  hide data loss).

## P3 — translation-fidelity gaps (known honest skips to revisit)

- [ ] OpenAI **Responses API** (`/v1/responses`) adapter — chat-completions only
  today; new SDK versions default to Responses for some features.
- [ ] Images/multimodal — the largest honest-skip category; even same-provider
  pass-through would unlock vision corpora.
- [x] Anthropic `tool_choice: {"type": "none"}` (0.11.0) — verified live
  (`tests/test_live_anthropic.py`): the API accepts the spelling and suppresses
  tool calls (paired with a forced-call control on identical input). Live note:
  with the only tool off the table, Haiku may answer with empty content — model
  disposition, faithfully decoded, not an adapter bug.
- [x] `parallel_tool_calls` and function `strict: true` (0.11.0) — carried
  same-dialect, dropped-with-a-note otherwise.
- [x] Strict `json_schema` migration for native targets (0.11.0) — OpenAI→OpenAI
  carries the schema; non-native targets skip honestly.

## P4 — project hygiene & distribution

- [ ] CONTRIBUTING.md (test conventions, invariants pointer to CLAUDE.md,
  snapshot-contribution process).
- [ ] CI: publish the sample HTML report as a build artifact. (The Windows
  runner is already in `.github/workflows/ci.yml` — the matrix proves the suite
  on ubuntu + windows across 3.10–3.13.)
- [x] PyPI metadata: description now leads with the migration positioning
  (keywords already include gemini/mistral).
- [ ] Launch blog post / Show HN around a real migration story — the report
  artifact is the hook.
