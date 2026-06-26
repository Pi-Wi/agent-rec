# Security Policy

## Supported versions

agentrec follows [SemVer](DEPRECATIONS.md); security fixes land on the latest
1.x release.

| Version | Supported |
|---|---|
| latest 1.x | ✅ |
| < 1.0 (pre-release) | ❌ |

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

Use GitHub's private reporting:
**[Security → Report a vulnerability](https://github.com/Pi-Wi/agent-rec/security/advisories/new)**.

Include the affected version, a description, and ideally a minimal reproduction.
I aim to acknowledge within a few business days and will coordinate a fix and a
disclosure timeline with you. agentrec is a small project — please allow
reasonable time to respond before any public disclosure.

## Threat model — the corpus is the sensitive artifact

agentrec's job is to **record real LLM API traffic** to disk and replay it. The
thing to protect is therefore the **corpus** (the cassette files), not the
library at runtime: a cassette can contain whatever your prompts and responses
contained. Treat a corpus like any other data export of production traffic — the
trust boundary is *writing a cassette to disk* and *sharing that corpus*.

agentrec applies best-effort scrubbing on write; everything beyond that is your
retention and review policy.

## What is and isn't scrubbed

`FileStore` scrubbing is a **best-effort safety net, not a guarantee.** Always
review a corpus before sharing it.

**Always redacted** — auth and cookie headers, matched by exact name on both
request and response, replaced with `[REDACTED]` (rebuilt requests take fresh
keys from the environment): `Authorization`, `Proxy-Authorization`, `Api-Key`,
`X-Api-Key`, `Cookie`, `Set-Cookie`.

**Scrubbed from request bodies and summaries by default** — known secret shapes
(`agentrec.DEFAULT_SECRET_PATTERNS`), including:

- OpenAI / Anthropic API keys (`sk-…`, `sk-ant-…`)
- AWS access-key ids (`AKIA…`)
- GitHub tokens (`ghp_/gho_/ghu_/ghs_/ghr_…`)
- Google API keys and OAuth tokens (`AIza…`, `ya29.…`)
- Slack tokens (`xox[baprs]-…`)
- JWTs and PEM `PRIVATE KEY` blocks
- URL-embedded credentials (`scheme://user:password@host`)
- `Bearer …` tokens
- JSON secret fields (`"password" / "api_key" / "secret" / "token" / "access_token": "…"`)

**NOT scrubbed by default:**

- **Response bodies are stored verbatim** — they are the replay source of truth.
  Pass `scrub_response_body=True` to run the same scrubber over responses when
  recording live traffic.
- **Anything not matching a known pattern** — a bare hex token, a custom auth
  scheme, or any secret shape not listed above passes through untouched.
- **Prompt and response content itself** (PII, business data) is recorded as-is.

## Recording live traffic safely

- **Prefer importing** an existing observability export (`agentrec import`) over
  running the recorder in your hot path — no new place for prompts to land.
- **Sample by prompt *shape*** — `semantic_key` grouping means one good
  recording per shape is enough for a full migration corpus.
- Set `scrub_response_body=True` and extend `secret_patterns=[...]` with your
  organisation's token shapes.
- **Set a retention policy** — cassettes are plain files; rotate, expire, and
  review them like any other data export.

See the README's "Recording live traffic" note and [DEPRECATIONS](DEPRECATIONS.md)
for the cassette-format stability guarantees.
