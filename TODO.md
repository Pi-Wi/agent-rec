# Roadmap — the road to 1.0

The live roadmap (referenced by `CLAUDE.md` and the `prime-context` skill).
**Shipped** work lives in `CHANGELOG.md`; this file is what's *left*. Priorities
follow the `TODO Pn` convention the changelog already cites (P0 = release
blocker, P3 = post-1.0).

The library is functionally mature at 0.11.0: record/replay (sync + async,
SSE + JSON), four translation dialects (OpenAI ↔ Anthropic ↔ Gemini ↔ Mistral),
tool-call + structured-output fidelity, derived cost/latency, CI on
Ubuntu **and** Windows across Python 3.10–3.13. What's missing for a *first
official release* is mostly the 1.0 commitment itself — API stability, the
release pipeline, typing/quality gates, and the community files — not engine
features.

> Roadmap note: the README "Roadmap" section lists "CI Windows runner" as open.
> It isn't — `.github/workflows/ci.yml` already runs a `windows-latest` matrix
> leg. Update that section when this file is adopted.

---

## P0 — blockers for cutting 1.0

The minimum to honestly publish a `1.0.0` to PyPI.

- [x] **Commit to a stable public API (the actual meaning of 1.0).** The README
  still says *"The API may still change in minor releases before 1.0."* Going
  1.0 means retiring that sentence and promising SemVer. Concretely: declare the
  public surface (the `__all__` in `agentrec/__init__.py` plus the documented CLI
  flags and cassette-on-disk format), and write a short **deprecation policy**
  (what can change in a minor, what waits for 2.0, how long deprecations live).
  *Why:* every other P0 is mechanical; this is the promise users actually rely
  on, and it constrains everything after.
- [ ] **Decide the cassette-format stability guarantee.** Corpora are meant to
  be *kept* (the "frozen behavioural baseline" in the README). State whether the
  on-disk JSON is part of the 1.0 contract and how `semantic_key` changes will
  be handled post-1.0 — the changelog already documents three pre-1.0 regroupings
  (0.3.0/0.4.0/0.6.0); after 1.0 those need a migration path, not a caveat.
- [ ] **Ship `py.typed`.** The package is thoroughly typed (dataclasses, typed
  returns throughout) but ships no marker, so downstream type-checkers ignore it
  entirely. Add `agentrec/py.typed` and include it in the wheel
  (`[tool.hatch.build]` force-include / package-data). *Why:* a typed library
  that doesn't advertise it gives consumers none of the benefit — and this is
  far cheaper to promise at 1.0 than to retrofit later.
- [ ] **Finalize version + changelog.** Bump `pyproject.toml` to `1.0.0`, roll
  the `## Dev (0.11.0)` heading to `## 1.0.0 — YYYY-MM-DD`, and move the
  classifier from `Development Status :: 4 - Beta` to `5 - Production/Stable`.
  Update the README status line (currently "beta (0.11.0)").
- [ ] **Release pipeline to PyPI.** No publish workflow exists (CI only tests).
  Add a tag-triggered GitHub Actions job that builds sdist + wheel, runs
  `twine check`, and publishes via **Trusted Publishing (OIDC)** — no API token
  in secrets. Smoke-test the built wheel in a clean env (`pip install`, run
  `agentrec report` on the shipped corpus) before publish.
- [ ] **Clean up `dist/`.** It holds stale `0.2.0`–`0.5.1` artifacts and is
  checked in. Add `dist/` to `.gitignore` and remove the committed wheels; build
  artifacts shouldn't live in the repo.

## P1 — strongly want before the first official release

Not strictly required to publish, but a 1.0 that ships without these looks
unfinished.

- [ ] **`CONTRIBUTING.md`.** Named in the README roadmap and still absent.
  Document the nested-repo layout, the venv test command
  (`.venv\Scripts\python.exe -m pytest -q`), the offline-by-default suite + how
  live tests opt in via `.env`, the changelog style, and the
  "new feature needs same-style tests" rule from `CLAUDE.md`.
- [ ] **`SECURITY.md` + documented secret-hygiene threat model.** The tool's
  entire scrubbing story is *"best-effort, not a guarantee — response bodies are
  verbatim unless you opt in."* A 1.0 that records API traffic needs a
  vulnerability-reporting channel and an explicit statement of what is and isn't
  scrubbed, so users make an informed call before sharing a corpus.
- [ ] **Lint + format gate in CI.** No linter/formatter is configured. Add
  `ruff` (lint + format) with config in `pyproject.toml` and a CI step. *Why:* a
  consistency floor that survives contributors; cheap to add now, noisy to add
  after a 1.0 freezes style expectations.
- [ ] **Type-check gate in CI.** Add `mypy` (or `pyright`) over `agentrec/` in
  CI. *Why:* `py.typed` (P0) is a promise; this is what keeps the promise true.
  Pairs naturally with the lint step.
- [ ] **Resolve the `requirements.txt` confusion.** It's a full `pip freeze`
  (pins `openai`, `anthropic`, `pytest`, `pydantic`, …) sitting next to the
  curated `[project.optional-dependencies]`. Two competing sources of truth.
  Either delete it (dev deps already live in the `dev` extra) or repurpose it as
  an explicitly-labelled, regenerated lockfile — don't ship both unexplained.

## P2 — should have / scope decisions for 1.0

Each needs a decision: *in 1.0, or explicitly deferred?* Stating the non-goals
is itself part of a clean release.

- [ ] **OpenAI Responses API (`/v1/responses`) dialect.** The README roadmap's
  top open item. The OpenAI SDK increasingly defaults new code to Responses, so
  corpora recorded today may already use it and currently fall back to the
  generic body hash (no translation). Decide: add the dialect for 1.0, or ship
  1.0 with chat-completions only and a documented limitation.
- [ ] **Coverage measurement.** Add coverage reporting (not necessarily a hard
  gate) so the 1.0 surface has a known number and regressions are visible. The
  suite is large (~5,700 LOC of tests) but unmeasured.
- [ ] **Public API reference / docs decision.** Today it's README + the two
  sample reports. Decide whether 1.0 needs a hosted docs site / generated API
  reference, or whether the README + `examples/` + docstrings are the
  documentation contract. If the latter, say so.
- [ ] **End-to-end release dry-run on a clean checkout.** Follow the published
  install path (`pip install agentrec`, then the README's "Try it now — no keys"
  flow) on a fresh machine/container to confirm the shipped corpus + entry point
  work as documented. Catches packaging gaps (missing package-data, the
  `pricing_data/` snapshots, the demo corpus) that local dev hides.

## P3 — post-1.0 / explicit non-goals

Reasonable to defer past the first release; list as known non-goals so users
aren't surprised.

- [ ] **Images / multimodal.** Currently an honest skip. State it as a 1.0
  non-goal and a 1.x target rather than leaving it ambiguous.
- [ ] **More providers / importers.** The adapter + importer seams are
  extension points by design (`register`, `SOURCES`); additions are minor-version
  work, not 1.0 blockers.
- [ ] **Community-file polish.** `CODE_OF_CONDUCT.md`, issue/PR templates — nice
  for an active OSS project, not gating a first release.
