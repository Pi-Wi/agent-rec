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
   `metadata` keys (`provider`, `model`, `semantic_key`, `recorded_at`,
   `latency_s`, `latency_first_chunk_s`, `category`, `imported`,
   `imported_from`, `migrated_from`). A cassette written by any 1.x release
   stays loadable by any later 1.y.

   This covers the *structure* only. The **algorithm** that computes
   `semantic_key` (what gets hashed, how it's normalized — the thing that
   decides which recordings group into the same migration row) is a separate,
   narrower guarantee — see "Requires a major release" below. The detailed
   mechanics of a post-1.0 `semantic_key` migration path are intentionally
   not designed in this document; that's the still-open TODO item "Decide the
   cassette-format stability guarantee."

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
  major-version event with a migration path, not a caveat — see the open
  "cassette-format stability guarantee" TODO item for how that path gets
  designed.
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

## See also

- [CHANGELOG.md](CHANGELOG.md) for the history of changes, including the
  pre-1.0 `semantic_key` regroupings this policy's major-release rule is
  modeled on.
- [TODO.md](TODO.md) for the open "cassette-format stability guarantee"
  item — the deeper mechanics of a post-1.0 `semantic_key` migration path,
  not designed in this document.
