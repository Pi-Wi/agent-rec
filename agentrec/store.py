"""
Abstract store interface and concrete implementations.

InMemoryStore — volatile, single-process.
FileStore     — one JSON file per interaction, so a corpus persists on disk
                and grows across runs.

Both satisfy the same interface without touching the transport code.  The
async methods are the primary interface (the async transports use them); the
``*_sync`` mirror serves the sync transports.  Both built-in stores are
natively synchronous, so each async method simply delegates to its sync twin.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from abc import ABC
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest


class InteractionStore(ABC):
    """Persistence contract for captured interactions.

    Implement **either** the synchronous trio (``save_sync`` / ``load_sync`` /
    ``discard_sync``) — the common case, and what both built-in stores do — **or**
    the async methods (``save`` / ``load`` / ``discard``).  Each async method
    delegates to its sync twin by default, so a synchronous store implements the
    ``*_sync`` methods once and gets the async interface (used by the async
    transports) for free; a natively-async store (e.g. a DB driver) overrides the
    async methods and may leave the sync twins raising ``NotImplementedError``.
    ``has`` / ``has_sync`` default to an existence probe via ``load`` /
    ``load_sync``; concrete stores override with a cheaper check.  Enumeration
    (``ids`` / ``__len__``) is synchronous — the corpus tooling iterates it
    directly — so a store must implement ``ids`` to be migrated or annotated.
    """

    # --- Async interface (used by the async transports) --------------------
    # Defaults delegate to the sync twin, so a synchronous store gets these for
    # free.  ``has`` probes ``load`` rather than ``has_sync`` so a natively-async
    # store (whose ``has_sync`` may raise) still gets a working existence check.

    async def save(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        self.save_sync(interaction_id, interaction)

    async def load(self, interaction_id: str) -> CapturedInteraction:
        return self.load_sync(interaction_id)

    async def discard(self, interaction_id: str) -> None:
        """Remove a recording if present (no error when absent).

        Lets tooling un-cache a recording that should not be replayed — e.g.
        the migration runner discards a failed (non-200) target response so a
        re-run retries the live call instead of replaying the failure.
        """
        self.discard_sync(interaction_id)

    async def has(self, interaction_id: str) -> bool:
        """Whether a recording exists. Drives auto mode (replay-or-record)."""
        try:
            await self.load(interaction_id)
            return True
        except KeyError:
            return False

    # --- Sync mirror (used by the sync transports) -------------------------
    # A custom store that is natively async (e.g. a DB driver) may leave these
    # unimplemented; the sync transports then fail with a clear message.

    def save_sync(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement the sync store interface; "
            "use the async transports with this store"
        )

    def load_sync(self, interaction_id: str) -> CapturedInteraction:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement the sync store interface; "
            "use the async transports with this store"
        )

    def discard_sync(self, interaction_id: str) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement the sync store interface; "
            "use the async transports with this store"
        )

    def has_sync(self, interaction_id: str) -> bool:
        try:
            self.load_sync(interaction_id)
            return True
        except KeyError:
            return False

    # --- Enumeration -------------------------------------------------------
    # Synchronous on both built-in stores; the corpus tooling (run_migration,
    # annotate_corpus) iterates ids() without awaiting.  The default raises a
    # clear error rather than an AttributeError, so a store that wants to be
    # migrated knows exactly what it must implement.

    def ids(self) -> List[str]:
        """Sorted ids of every interaction in the store.

        The migration runner and ``annotate_corpus`` enumerate the corpus
        through this, so a store that wants to be migrated must implement it.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement ids(); a store must be "
            "enumerable to be migrated or annotated"
        )

    def __len__(self) -> int:
        """Number of interactions in the store (defaults to ``len(self.ids())``)."""
        return len(self.ids())

    def __bool__(self) -> bool:
        # A store object is always truthy.  Without this, defining __len__ makes
        # an *empty* store falsy, silently flipping the common "if store:" /
        # "... if store else None" presence checks (e.g. the judge verdict cache,
        # which caches into an initially-empty store).  Presence is `is not None`;
        # emptiness is `len(store) == 0`.
        return True


class InMemoryStore(InteractionStore):
    """Volatile, single-process store — the first implementation."""

    def __init__(self) -> None:
        self._data: Dict[str, CapturedInteraction] = {}

    def save_sync(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        self._data[interaction_id] = interaction

    def load_sync(self, interaction_id: str) -> CapturedInteraction:
        try:
            return self._data[interaction_id]
        except KeyError:
            raise KeyError(
                f"No recorded interaction for id={interaction_id!r}. "
                "Run the record phase before replaying."
            ) from None

    def discard_sync(self, interaction_id: str) -> None:
        self._data.pop(interaction_id, None)

    def has_sync(self, interaction_id: str) -> bool:
        return interaction_id in self._data

    def __contains__(self, interaction_id: str) -> bool:
        return interaction_id in self._data

    async def has(self, interaction_id: str) -> bool:
        return self.has_sync(interaction_id)  # O(1) dict probe, cheaper than load

    def ids(self) -> List[str]:
        return sorted(self._data)

    def __len__(self) -> int:
        return len(self._data)


# ---------------------------------------------------------------------------
# On-disk store
# ---------------------------------------------------------------------------

# Headers that must never be written to a shareable corpus.  Request auth
# headers are ignored by replay entirely, and response Set-Cookie values
# (e.g. CDN session cookies) are not consumed by any SDK, so redacting both
# costs nothing and keeps secrets out of the cassette files.  Note the
# (deliberate) replay divergence: a replayed response carries the literal
# value "[REDACTED]" for these headers, not what the server originally sent.
_REDACTED_HEADERS = frozenset(
    {b"authorization", b"proxy-authorization", b"api-key", b"x-api-key", b"cookie", b"set-cookie"}
)
_REDACTED_VALUE = b"[REDACTED]"

# Characters allowed in a cassette filename; everything else becomes "_".
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")

Scrubber = Callable[[str], str]

# Secrets that may end up in a *request body* (e.g. a prompt that pastes an API
# key or password).  Applied to the request content before it is written.
#
# This is a BEST-EFFORT safety net, not a guarantee: it catches well-known key
# shapes, but a bare hex token, a custom auth scheme, or a secret format not
# listed here will pass through untouched.  Review cassettes before sharing a
# corpus, and pass ``secret_patterns=[...]`` to add organisation-specific
# shapes.  Order matters: more specific patterns (anthropic) run before the
# broader sk- rule.
DEFAULT_SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"), "[REDACTED-ANTHROPIC-KEY]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "[REDACTED-OPENAI-KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED-AWS-KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "[REDACTED-GITHUB-TOKEN]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "[REDACTED-GOOGLE-KEY]"),
    (re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}"), "[REDACTED-GOOGLE-TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED-SLACK-TOKEN]"),
    # JWTs: three base64url segments, the first two starting with the {"...
    # header/payload marker "eyJ".
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"),
        "[REDACTED-JWT]",
    ),
    # PEM private-key blocks (multi-line; pasted into a prompt verbatim).
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED-PRIVATE-KEY]",
    ),
    # URL credentials: scheme://user:password@host
    (
        re.compile(r"\b([a-z][a-z0-9+.\-]*://[^/\s:@\"']+):[^@\s\"']+@"),
        r"\1:[REDACTED]@",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED]"),
    # JSON-style secret fields: "password": "...", "api_key": "...", "token": "...".
    # The \\? allows escaped quotes, so it also catches a JSON blob that was
    # itself embedded (and thus escaped) inside another JSON string.
    (
        re.compile(
            r'(?i)(\\?"(?:api[_-]?key|password|secret|token|access[_-]?token)\\?"\s*:\s*\\?")[^"\\]*(\\?")'
        ),
        r"\1[REDACTED]\2",
    ),
]


def scrub_secrets(
    text: str, patterns: Optional[List[Tuple[re.Pattern, str]]] = None
) -> str:
    """Redact known secret shapes from *text* (best-effort; see pattern notes)."""
    for pattern, replacement in (patterns or DEFAULT_SECRET_PATTERNS):
        text = pattern.sub(replacement, text)
    return text


# --- Readable blob encoding -------------------------------------------------
# A "blob" is a known-bytes field (header name/value, chunk data, request body).
# We store it as a plain JSON string when it is valid UTF-8 so the corpus is
# human-readable, and fall back to a tagged base64 object only for genuinely
# binary data (e.g. a chunk that splits a multibyte character).


def _encode_blob(data: bytes, *, scrub: Optional[Scrubber] = None):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"__b64__": base64.b64encode(data).decode("ascii")}
    return scrub(text) if scrub else text


def _decode_blob(value) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return base64.b64decode(value["__b64__"])


def _encode_headers(headers: List[Tuple[bytes, bytes]]) -> list:
    out = []
    for name, value in headers:
        if name.lower() in _REDACTED_HEADERS:
            value = _REDACTED_VALUE
        out.append([_encode_blob(name), _encode_blob(value)])
    return out


def _decode_headers(pairs: list) -> List[Tuple[bytes, bytes]]:
    return [(_decode_blob(name), _decode_blob(value)) for name, value in pairs]


def _encode_extensions(ext: dict) -> dict:
    """Readable view of response.extensions; bytes are tagged but kept legible."""
    out: dict = {}
    for key, value in ext.items():
        if isinstance(value, bytes):
            try:
                out[key] = {"__bytes__": value.decode("utf-8")}
            except UnicodeDecodeError:
                out[key] = {"__b64__": base64.b64encode(value).decode("ascii")}
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)  # last-resort: keep the file serialisable
    return out


def _decode_extensions(ext: dict) -> dict:
    out: dict = {}
    for key, value in ext.items():
        if isinstance(value, dict) and "__bytes__" in value:
            out[key] = value["__bytes__"].encode("utf-8")
        elif isinstance(value, dict) and "__b64__" in value:
            out[key] = base64.b64decode(value["__b64__"])
        else:
            out[key] = value
    return out


def _build_summary(
    interaction: CapturedInteraction, *, scrub: Optional[Scrubber] = None
) -> dict:
    """Derived, human-readable summary block — empty dict when undecodable.

    Purely a convenience layer: it is written first in the cassette so the
    file opens with the prompt and answer in plain text, and it is ignored on
    load (raw chunks stay the replay source of truth).  Never allowed to make
    a save fail.
    """
    try:
        from .providers import build_summary

        summary = build_summary(interaction)
    except Exception:
        return {}
    if scrub:
        for key in ("prompt", "response"):
            if isinstance(summary.get(key), str):
                summary[key] = scrub(summary[key])
    return summary


def _interaction_to_dict(
    interaction: CapturedInteraction,
    *,
    scrub: Optional[Scrubber] = None,
    scrub_response: Optional[Scrubber] = None,
) -> dict:
    req = interaction.request
    out: dict = {}
    summary = _build_summary(interaction, scrub=scrub)
    if summary:
        # Readability first: a cassette opens with the decoded prompt/response.
        out["summary"] = summary
    out.update({
        # Provenance next so provider/model/semantic_key stay visible — the
        # fields a migration report groups and compares on.
        "metadata": interaction.metadata,
        "request": {
            "method": req.method,
            "url": req.url,
            "headers": _encode_headers(req.headers),
            "content": _encode_blob(req.content, scrub=scrub),
        },
        "response_status": interaction.response_status,
        "response_headers": _encode_headers(interaction.response_headers),
        "response_extensions": _encode_extensions(interaction.response_extensions),
        # Raw chunks are the replay source of truth; they are only scrubbed
        # when the caller opts in (it alters the bytes replay will serve).
        "chunks": [
            {"data": _encode_blob(c.data, scrub=scrub_response), "timestamp_offset": c.timestamp_offset}
            for c in interaction.chunks
        ],
    })
    return out


def _interaction_from_dict(d: dict) -> CapturedInteraction:
    req = d["request"]
    return CapturedInteraction(
        request=CapturedRequest(
            method=req["method"],
            url=req["url"],
            headers=_decode_headers(req["headers"]),
            content=_decode_blob(req["content"]),
        ),
        response_status=d["response_status"],
        response_headers=_decode_headers(d["response_headers"]),
        response_extensions=_decode_extensions(d["response_extensions"]),
        chunks=[
            CapturedChunk(data=_decode_blob(c["data"]), timestamp_offset=c["timestamp_offset"])
            for c in d["chunks"]
        ],
        metadata=d.get("metadata", {}),  # tolerate pre-metadata cassettes
    )


class FileStore(InteractionStore):
    """
    Persists each interaction as a human-readable ``<root>/<interaction_id>.json``.

    The corpus survives between processes and grows as new interactions are
    recorded.  Writes are atomic (temp file + replace) so a crash mid-write
    can't leave a half-written cassette behind.

    Content (request body, SSE chunks, headers) is stored as plain UTF-8 text so
    a cassette can be read and verified by eye; only genuinely binary fragments
    fall back to base64.

    Secret handling (best-effort — review cassettes before sharing a corpus):

    * Auth headers are always redacted (exact-name match, reliable).
    * Known secret *shapes* are scrubbed from the request body and from the
      derived summary by default — pass ``scrub_request_body=False`` to
      disable, or ``secret_patterns=[...]`` to supply your own.  Shapes not in
      the pattern list pass through untouched.
    * Raw response chunks are stored **verbatim** by default (they are the
      bytes replay serves).  A response that echoes a secret therefore lands
      on disk unless you opt in with ``scrub_response_body=True`` — which
      scrubs each chunk's text best-effort (a secret split across two chunks,
      or inside a compressed body, is not caught).
    """

    def __init__(
        self,
        root: str | Path,
        *,
        scrub_request_body: bool = True,
        scrub_response_body: bool = False,
        secret_patterns: Optional[List[Tuple[re.Pattern, str]]] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        scrubber: Scrubber = lambda t: scrub_secrets(t, secret_patterns)
        self._scrub: Optional[Scrubber] = scrubber if scrub_request_body else None
        self._scrub_response: Optional[Scrubber] = scrubber if scrub_response_body else None

    def _path(self, interaction_id: str) -> Path:
        # Sanitize anything that could escape the corpus dir or trip up a
        # filesystem: path separators, colons (NTFS streams / drive-relative
        # paths on Windows) and other reserved characters.
        safe = _UNSAFE_FILENAME_CHARS.sub("_", interaction_id) or "x"
        if safe != interaction_id:
            # Sanitization is lossy ("a/b" and "a_b" would collide on the same
            # file); a short digest of the original id keeps distinct ids
            # distinct on disk.
            digest = hashlib.sha256(interaction_id.encode("utf-8")).hexdigest()[:8]
            safe = f"{safe}-{digest}"
        return self.root / f"{safe}.json"

    def save_sync(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        path = self._path(interaction_id)
        text = json.dumps(
            _interaction_to_dict(
                interaction, scrub=self._scrub, scrub_response=self._scrub_response
            ),
            indent=2,
            ensure_ascii=False,
        )
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def load_sync(self, interaction_id: str) -> CapturedInteraction:
        path = self._path(interaction_id)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise KeyError(
                f"No recorded interaction for id={interaction_id!r} in {self.root}. "
                "Run the record phase before replaying."
            ) from None
        return _interaction_from_dict(json.loads(text))

    def discard_sync(self, interaction_id: str) -> None:
        try:
            self._path(interaction_id).unlink()
        except FileNotFoundError:
            pass

    def has_sync(self, interaction_id: str) -> bool:
        return self._path(interaction_id).exists()

    def __contains__(self, interaction_id: str) -> bool:
        return self._path(interaction_id).exists()

    async def has(self, interaction_id: str) -> bool:
        # Cheap existence check (a stat), not the ABC default's full load+parse.
        return self.has_sync(interaction_id)

    def ids(self) -> List[str]:
        """Sorted interaction ids currently on disk.

        These are the on-disk file stems.  Every id the library mints
        (fingerprint cassette ids, ``migration__`` / ``judge__`` / ``imported__``
        ids) is already filename-safe, so it round-trips here unchanged.  A
        *custom* ``id=`` containing path-unsafe characters is stored under a
        sanitized ``<safe>-<digest8>`` stem (see :meth:`_path`); ``ids`` then
        returns that stem, not the original string — re-load via the returned
        value, which keys back to the same file.
        """
        return sorted(p.stem for p in self.root.glob("*.json"))

    def __len__(self) -> int:
        return sum(1 for _ in self.root.glob("*.json"))
