# Examples

Runnable scripts that build a corpus and migrate it. Run them from the project
root with the project venv; recording needs `OPENAI_API_KEY` (and migrating
needs `ANTHROPIC_API_KEY`), both read from a repo-root `.env`. A re-run replays
already-recorded prompts instead of paying for them again.

| File | What it shows |
|---|---|
| [`generate_corpus_and_migrate.py`](generate_corpus_and_migrate.py) | **Text-corpus migration.** Records 100 production-shaped `gpt-4o-mini` prompts (classify / extract / summarize / rewrite / translate), migrates them to a Claude target, and renders the report with per-category and cost columns. This is the corpus behind [`docs/sample-report.md`](../docs/sample-report.md). |
| [`tool_calling_migration.py`](tool_calling_migration.py) | **Tool-calling agent step.** Records one-step agent decisions over a `get_weather` tool, migrates cross-provider, and scores *tool selection + arguments* with the offline `toolcalls` comparator (tools are never executed). |
| [`ci-regression-gate.yml`](ci-regression-gate.yml) | **CI workflow snippet.** A GitHub Actions job that gates every prompt/model change against a committed corpus with `--strict --min-pass` — offline, no API keys. Copy into `.github/workflows/`. |
| [`grow_corpus.py`](grow_corpus.py) | Record-only helper: appends a batch of streamed interactions to a `corpus/` so it accumulates across runs. |

```bash
# text-corpus migration (smoke test with --limit)
.venv\Scripts\python.exe examples\generate_corpus_and_migrate.py --limit 10 --format all

# tool-calling agent step
.venv\Scripts\python.exe examples\tool_calling_migration.py
```
