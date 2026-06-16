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
- [ ] CI: publish the sample HTML report as a build artifact; add a Windows runner
  (suite is developed on Windows but CI should prove it).
- [ ] PyPI metadata: description still says "record/replay" — align with the
  migration positioning (keywords already include gemini/mistral).
- [ ] Launch blog post / Show HN around a real migration story — the report
  artifact is the hook.
