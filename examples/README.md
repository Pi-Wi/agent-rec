# Examples

Runnable scripts that build a corpus and migrate it. Run them from the project
root with the project venv; recording needs `OPENAI_API_KEY` and migrating needs
the target provider's key (`ANTHROPIC_API_KEY` for Claude targets, or
`GEMINI_API_KEY` / `GOOGLE_API_KEY` for the Gemini example) — all read from a
repo-root `.env`. A re-run replays already-recorded prompts instead of paying
for them again.

| File | What it shows |
|---|---|
| [`generate_corpus_and_migrate.py`](generate_corpus_and_migrate.py) | **Text-corpus migration.** Records 100 production-shaped `gpt-4o-mini` prompts (classify / extract / summarize / rewrite / translate), migrates them to a Claude target, and renders the report with per-category and cost columns. This is the corpus behind [`docs/sample-report.md`](../docs/sample-report.md). |
| [`tool_calling_migration.py`](tool_calling_migration.py) | **Tool-calling agent step.** Records one-step agent decisions over a `get_weather` tool, migrates cross-provider, and scores *tool selection + arguments* with the offline `toolcalls` comparator (tools are never executed). |
| [`multi_turn_agent_migration.py`](multi_turn_agent_migration.py) | **Multi-turn agent transcript (step-wise).** Records a support agent *loop* — `look_up_order` → `get_shipping_events` → `issue_refund`/`escalate_to_human` → reply — against a canned back-end, then migrates it to Claude. Each turn (with the conversation and tool results so far) becomes its own scored row: `toolcalls` grades the tool-calling steps, `fuzzy` the closing reply. This is the step-wise multi-turn methodology in action — "at this point in the conversation, does the new model take the same next action?" |
| [`gemini_tool_calling_migration.py`](gemini_tool_calling_migration.py) | **Tool-calling agent migrated to Gemini.** Records an OpenAI customer-support agent (`look_up_order` / `issue_refund` / `escalate_to_human`), migrates it to a **Gemini** target, and scores *tool selection + arguments* with `toolcalls` — "would Gemini make the same tool decisions on the same tickets?" (Gemini can't be recorded — its SDK bypasses httpx — so it's the migration target; for the reverse direction use `agentrec import`.) |
| [`import_observability_export.py`](import_observability_export.py) | **Import an observability export (no recorder, no SDK).** Synthesizes a deliberately *messy* Langfuse export, brings it in with `agentrec import`, and shows the whole no-recorder path: provenance metadata, cross-provider `semantic_key` grouping, and honest skips. **Import + inspect run with no API keys** (offline); `--migrate` re-asks the target. Goes hard on the edges — PII/secret scrubbing (the hardening the CLI can't do), non-LLM spans, empty/system-only inputs, and an image-only turn the importer skips honestly (text dropped, nothing left to ask) rather than synthesizing an empty prompt that would 400 the target. |
| [`ci-regression-gate.yml`](ci-regression-gate.yml) | **CI workflow snippet.** A GitHub Actions job that gates every prompt/model change against a committed corpus with `--strict --min-pass` — offline, no API keys. Copy into `.github/workflows/`. |
| [`grow_corpus.py`](grow_corpus.py) | Record-only helper: appends a batch of streamed interactions to a `corpus/` so it accumulates across runs. |

```bash
# text-corpus migration (smoke test with --limit)
.venv\Scripts\python.exe examples\generate_corpus_and_migrate.py --limit 10 --format all

# tool-calling agent step (OpenAI -> Claude)
.venv\Scripts\python.exe examples\tool_calling_migration.py

# multi-turn agent transcript, scored step-by-step (OpenAI -> Claude)
.venv\Scripts\python.exe examples\multi_turn_agent_migration.py

# tool-calling agent step migrated to Gemini (OpenAI -> gemini-2.5-flash)
.venv\Scripts\python.exe examples\gemini_tool_calling_migration.py

# import an observability export — import + inspect run offline, no API keys
.venv\Scripts\python.exe examples\import_observability_export.py
# ...then re-ask the target live (needs the target provider's key):
.venv\Scripts\python.exe examples\import_observability_export.py --migrate
```
