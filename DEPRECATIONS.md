# Deprecation & API Stability Policy

agentrec follows [Semantic Versioning](https://semver.org/) from 1.0.0
onward. This document defines what that promise covers and how changes are
made.

## What's covered

Three surfaces are covered by SemVer:

1. **Python symbols** — everything listed in `agentrec.__all__`
   (`agentrec/__init__.py`) and in `agentrec.providers.__all__`
   (`agentrec/providers/__init__.py`): the data classes (`Conversation`,
   `DecodedResponse`, `TokenUsage`, …), the stores (`FileStore`,
   `InMemoryStore`, `InteractionStore`, `scrub_secrets`,
   `DEFAULT_SECRET_PATTERNS`), the transports, `session`'s facade
   (`async_client`/`sync_client`/`cassette`), the provider adapters and
   registry functions, comparators, `run_migration`/`annotate_corpus`,
   `import_corpus`, the pricing classes, and the report renderers.
2. **The CLI** — the five subcommands (`migrate`, `report`, `annotate`,
   `import`, `profiles`) and every flag documented in `agentrec <command>
   --help`: names, defaults, and semantics (e.g. that `--pricing` is
   repeatable and composes profiles with `a+b`, that `--strict` exits 1 on a
   failed gate, that `--min-pass` is keyed by comparator name).
3. **The cassette on-disk JSON structure** — the top-level fields a `FileStore`
   cassette writes (`summary`, `metadata`, `request`, `response_status`,
   `response_headers`, `response_extensions`, `chunks`) and the conventional
   `metadata` keys (`provider`, `model`, `semantic_key`,
   `semantic_key_version`, `recorded_at`, `latency_s`,
   `latency_first_chunk_s`, `category`, `imported`, `imported_from`,
   `migrated_from`). A cassette written by any 1.x release stays loadable by
   any later 1.y.

   This covers the *structure* only. The **algorithm** that computes
   `semantic_key` (what gets hashed, how it's normalized — the thing that
   decides which recordings group into the same migration row) is a separate,
   narrower guarantee — see "Requires a major release" below and the dedicated
   section ["Semantic-key stability & the 2.0 migration
   path"](#semantic-key-stability--the-20-migration-path), which defines how a
   post-1.0 algorithm change is handled.

## What's NOT covered

Anything importable but not listed in either `__all__` is internal and may
change in any release, including a patch. Today that includes: the type
aliases `Keyer`/`KeyLike`/`ExtraMetadata` (`transport.py`) and `Mode`
(`session.py`); `PricingArg` and `default_report_basename()` (`report.py`);
`ALL_COMPARATOR_NAMES`/`OFFLINE_COMPARATOR_NAMES`/`JUDGE_PREFIX`
(`comparators.py`); `MIGRATION_PREFIX` (`migration.py`); and any
leading-underscore name anywhere. (The type aliases are a candidate for
promotion once `py.typed` ships — tracked separately, not decided here.)

## Safe in a minor release (1.x → 1.(x+1))

- Adding a new `__all__` symbol, CLI flag, or subcommand.
- Adding a new top-level cassette JSON field, or a new conventional
  `metadata` key.
- Adding a new built-in provider adapter, comparator, importer source, or
  pricing profile.
- Loosening a previously-required input (a flag becoming optional, a
  validation becoming more permissive).
- Bug fixes that make behavior match its documented contract.
- Performance improvements that don't change observable output.

## Requires a major release (2.0)

- Removing or renaming any `__all__` symbol, CLI flag, subcommand, or
  top-level cassette JSON field.
- Changing an existing CLI flag's meaning or default in a way that changes
  output for existing invocations.
- Changing an existing function/class signature in a way that breaks an
  existing call (positional reordering, removing a parameter, narrowing an
  accepted type).
- **Any change to the `semantic_key` algorithm** that would regroup an
  existing corpus differently. Pre-1.0, three such regroupings shipped as
  documented `CHANGELOG.md` caveats (0.3.0, 0.4.0, 0.6.0); post-1.0 this is a
  major-version event with a migration path, not a caveat — bumping
  `SEMANTIC_KEY_VERSION` and shipping a re-key step, as defined in
  ["Semantic-key stability & the 2.0 migration
  path"](#semantic-key-stability--the-20-migration-path).
- Dropping support for a Python version still inside its upstream support
  window.

## Deprecation lifecycle

1. The replacement ships first, available alongside the deprecated path.
2. The deprecated path keeps working but warns: a `DeprecationWarning` for
   Python API, a one-line stderr notice for a CLI flag — both naming the
   replacement.
3. The same release's `CHANGELOG.md` entry gets a `### Deprecated`
   subsection saying what's deprecated, why, and the replacement.
4. The deprecated path is kept for a minimum of **two minor releases** after
   the warning first ships, and is only removed in a major release — never
   silently dropped in a minor.
5. Removal is its own `CHANGELOG.md` entry, under `### Removed`,
   cross-referencing the release that introduced the deprecation.

## Cassette compatibility commitment

A cassette or corpus directory written by any 1.x release loads and replays
correctly under any later 1.y release. Forward structural compatibility (new
optional fields) is unconditional within 1.x. Reading a cassette written by a
*newer* 1.y under an *older* 1.x is best-effort — unknown fields are ignored,
the same tolerance `store.py` already extends to cassettes recorded before
`metadata` existed — but it isn't guaranteed.

That commitment is about the on-disk *structure* (load + replay). The
*grouping* a corpus produces in a migration report — which recordings are
treated as the same logical prompt — is governed separately by the
`semantic_key` algorithm, covered next.

## Semantic-key stability & the 2.0 migration path

A corpus is meant to be **kept** — a frozen behavioural baseline that gates
every prompt edit and model bump in CI. So the question isn't only "does the
file still load," but "does it still group into the same rows." That grouping
is the `semantic_key`, and its stability rests on three facts:

1. **The running release's algorithm is the grouping authority.** The migration
   runner recomputes each baseline's `semantic_key` from the request bytes with
   the algorithm in the release you're running — it does **not** group by the
   key pinned in a cassette's metadata. The pinned `semantic_key` is
   recording-time *provenance* (shown in summaries and the report); the live
   recompute is what groups. This is *why* a corpus recorded by an old release
   still groups correctly today: the runner re-derives every key under the
   current rules, so a corpus never carries a stale grouping forward.

2. **That algorithm is frozen across all of 1.x.** Because the runner recomputes
   with a fixed algorithm, every 1.x release groups a given corpus
   *identically*. Changing what `semantic_key` hashes or how it normalizes —
   anything that would regroup an existing corpus — is a **2.0** event (see
   "Requires a major release"), never a minor or patch.

3. **Every 1.x recording is version-stamped.** Cassettes written by the recorder
   and by `agentrec import` carry `semantic_key_version` in metadata (the value
   of `agentrec.SEMANTIC_KEY_VERSION`, currently **1**) — the algorithm that
   produced the co-located key. This stamp is the part that *cannot* be added
   retroactively, which is why 1.0 ships it: it makes a corpus self-identifying
   so a future major release can tell which algorithm grouped it.

**The 2.0 migration path.** When a future major release changes the algorithm,
it: (a) bumps `SEMANTIC_KEY_VERSION`; (b) ships an explicit **re-key** step that
recomputes and re-pins keys under the new algorithm (via `agentrec annotate`),
so adopting the new grouping is a deliberate action, not an accident of
upgrading; and (c) relies on a guard that **already ships in 1.x**: when the
migration runner reads a corpus whose stamped `semantic_key_version` differs
from the running release's, it emits a non-gating **warning** in the report
(naming both versions) and regroups under the running algorithm — it never
*silently* regroups a kept corpus. The warning is dormant throughout 1.x (one
frozen version) and becomes the visible signal at the 2.0 boundary. Like cost
and latency, the warning is informational and never affects a `--strict` gate.

## See also

- [CHANGELOG.md](CHANGELOG.md) for the history of changes, including the
  pre-1.0 `semantic_key` regroupings this policy's major-release rule is
  modeled on.
