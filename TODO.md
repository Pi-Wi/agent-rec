# TODO — roadmap to a recommendable 1.0

Priorities from the 2026-06 product review. Ordering principle: the engine is
strong; what limits the project is **how corpora get in** (funnel), **who can
use it** (provider coverage), and **how it presents itself** (positioning).

## P0 — positioning & first impression (cheap, highest leverage)

- [x] **Reposition the README around migration testing.** Lead with the
  decision the tool supports ("will the new model break my prompts, and what
  will it cost?") and the zero-authoring dataset insight ("your recorded
  traffic is your eval set"). Demote record/replay to the "how the corpus is
  built" section, pitched as infrastructure plus a free side benefit
  (deterministic offline tests). Name the trigger events (deprecation notice,
  new model release, price change) in the first paragraph.
- [x] **Put a rendered sample report above the fold.** Screenshot of the HTML
  report (or a trimmed markdown report) right after the 30-second demo:
  record → `agentrec migrate` → `agentrec report --strict --min-pass`. The
  report is the product; today a repo visitor never sees one.
  _(Done: real 100-prompt report committed to `docs/sample-report.{md,html}`,
  trimmed excerpt embedded above the fold, full versions linked.)_
- [x] **Frame the recurring use case, not just the episodic one.** Migration
  is a few-times-a-year event; "gate every prompt change and model swap in CI
  against your recorded corpus" is weekly. Same machinery (`semantic_key`
  groups across parameter changes) — document the prompt-regression workflow
  explicitly so the tool earns a permanent place in CI.
  _(Done: "Two ways to use it" + CI gate section in README.)_
- [x] Add 2–3 runnable examples under `examples/` (currently gitignored —
  decide: ship curated examples or drop the ignore entry): a text corpus
  migration, a tool-calling agent step, a CI workflow snippet with
  `--strict --min-pass`.
  _(Done: dropped the `examples/` ignore entry and shipped the curated set —
  `generate_corpus_and_migrate.py` (text), `tool_calling_migration.py` (tools),
  `ci-regression-gate.yml` (CI), plus `examples/README.md`.)_

## P1 — widen the funnel (the adoption bottleneck)

- [x] **Corpus importers from observability exports.** `agentrec import`
  for Langfuse/LangSmith exports and OTel GenAI spans → cassettes. This is
  the single highest-impact feature: it lets teams bring months of real
  production traffic to the migration runner **without running the recorder
  in prod** (no perf/PII objections, no code change). Design notes: imported
  interactions won't have raw SSE bytes — introduce a synthesized-JSON
  cassette form and mark provenance (`imported_from`) honestly.
  _(Done 0.8.0: `agentrec import --source langfuse|langsmith|otel|auto`;
  `importers.py` synthesizes OpenAI-dialect JSON cassettes (`imported_from` /
  `imported` metadata, `IMPORT_PREFIX`), best-effort with honest per-record
  skips. Uniform dialect preserves cross-provider `semantic_key` grouping.)_
- [x] **Gemini adapter** (third dialect). It's the first question under the
  migration positioning; OpenAI↔Anthropic↔Gemini is the triangle teams
  actually evaluate. Needs live verification against the API (tool calls,
  streaming, usage normalization). Check which SDK paths route through httpx;
  if none do, Gemini may be importer-only at first — that's still valuable.
  _(Done 0.8.0: `providers/gemini.py` (generateContent dialect — contents/
  parts, systemInstruction, functionDeclarations/Call/Response, usageMetadata,
  SSE) + offline tests. Core paths (non-streaming, streaming, tool calls,
  usage) **live-verified** against gemini-2.5-flash via
  `tests/test_live_gemini.py`; tool-result/JSON-mode build remain offline-only.
  The Gemini SDK doesn't route through httpx, so import / use-as-target is the
  path for getting Gemini traffic in.)_
- [x] **Document the prod-recording story** (even if the answer is "don't").
  Sampling, `scrub_response_body=True`, `secret_patterns`, retention. If the
  importer ships first, point to it as the recommended path.
  _(Done 0.8.0: README "Recording in production (and why you might not)" +
  "Importing an existing observability export" sections; points at the
  importer as the recommended path.)_

## P2 — complete the decision document

- [ ] **OpenRouter-fed pricing snapshot refresh.** A script (or CI cron) that
  generates dated snapshot JSONs from the OpenRouter API + a CONTRIBUTING
  note for community-submitted snapshots. Stale built-in prices erode trust
  faster than missing ones.
- [ ] **Latency for streamed targets.** Migration target calls are
  non-streaming today, so `latency_first_chunk_s` ≈ `latency_s` for targets
  while streamed baselines report true TTFB. Either request streamed targets
  (closer to prod behaviour) or surface only comparable numbers per row.
- [ ] **Judge robustness:** make the default judge model configurable via env
  (`AGENTREC_JUDGE_MODEL`), and consider a second-opinion mode (two judges,
  disagreement flagged) for gate-critical corpora.
- [ ] **Embedding comparator beyond OpenAI** (it currently requires an OpenAI
  key even for Anthropic→Anthropic migrations). Either support other
  embedding providers or document the dependency loudly.

## P3 — translation-fidelity gaps (known honest skips to revisit)

- [ ] OpenAI **Responses API** (`/v1/responses`) adapter — chat-completions
  only today; new SDK versions default to Responses for some features.
- [ ] `parallel_tool_calls` and function `strict: true` are silently dropped
  in translation — decide: carry them (same-provider), note them on the row,
  or keep dropping with a documented rationale.
- [ ] Strict `json_schema` migration for targets that support it natively
  (OpenAI→OpenAI should not need to skip).
- [ ] Images/multimodal — currently the largest honest-skip category. Even
  pass-through for same-provider migrations would unlock vision corpora.
- [ ] Anthropic `tool_choice: {"type": "none"}` translation is emitted but
  untested against the live API — verify in the next live-test run.

## P4 — project hygiene & distribution

- [ ] CONTRIBUTING.md (test conventions, invariants pointer to CLAUDE.md,
  snapshot-contribution process).
- [ ] CI: publish the sample HTML report as a build artifact so every PR
  shows what reports look like; add a Windows runner (the suite is developed
  on Windows but CI coverage should prove it).
- [ ] PyPI metadata: keywords/description still say "record/replay" — align
  with the new positioning when the README lands.
- [ ] Write the launch blog post / Show HN around a real migration story
  ("we replayed N recorded prompts against <new model>: here's the report")
  — the report artifact is the hook.

## Done (0.6.0, for context)

- [x] Tool-call translation (OpenAI ↔ Anthropic), `toolcalls` comparator
  (selection + arguments, never executes).
- [x] Latency capture (`latency_s`, `latency_first_chunk_s`) + report columns.
- [x] Step-wise multi-turn methodology documented in README.
- [x] CLAUDE.md contributor context; CLAUDE.local.md for machine-local notes.
