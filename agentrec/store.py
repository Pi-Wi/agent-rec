"""
Abstract store interface and concrete implementations.

InMemoryStore — volatile, single-process.
FileStore     — one JSON file per interaction, so a corpus persists on disk
                and grows across runs.

Both satisfy the same interface without touching the transport code.
"""
from __future__ import annotations

import base64
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest


class InteractionStore(ABC):
    @abstractmethod
    async def save(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        ...

    @abstractmethod
    async def load(self, interaction_id: str) -> CapturedInteraction:
        ...

    async def discard(self, interaction_id: str) -> None:
        """Remove a recording if present (no error when absent).

        Lets tooling un-cache a recording that should not be replayed — e.g.
        the migration runner discards a failed (non-200) target response so a
        re-run retries the live call instead of replaying the failure.
        """

    async def has(self, interaction_id: str) -> bool:
        """Whether a recording exists. Drives auto mode (replay-or-record).

        Default implementation probes ``load``; concrete stores override with a
        cheaper existence check.
        """
        try:
            await self.load(interaction_id)
            return True
        except KeyError:
            return False


class InMemoryStore(InteractionStore):
    """Volatile, single-process store — the first implementation."""

    def __init__(self) -> None:
        self._data: Dict[str, CapturedInteraction] = {}

    async def save(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        self._data[interaction_id] = interaction

    async def load(self, interaction_id: str) -> CapturedInteraction:
        try:
            return self._data[interaction_id]
        except KeyError:
            raise KeyError(
                f"No recorded interaction for id={interaction_id!r}. "
                "Run the record phase before replaying."
            ) from None

    def __contains__(self, interaction_id: str) -> bool:
        return interaction_id in self._data

    async def has(self, interaction_id: str) -> bool:
        return interaction_id in self._data

    async def discard(self, interaction_id: str) -> None:
        self._data.pop(interaction_id, None)


# ---------------------------------------------------------------------------
# On-disk store
# ---------------------------------------------------------------------------

# Headers that must never be written to a shareable corpus.  Request auth
# headers are ignored by replay entirely, and response Set-Cookie values
# (e.g. CDN session cookies) are not consumed by any SDK, so redacting both
# costs nothing and keeps secrets out of the cassette files.
_REDACTED_HEADERS = frozenset(
    {b"authorization", b"proxy-authorization", b"api-key", b"x-api-key", b"cookie", b"set-cookie"}
)
_REDACTED_VALUE = b"[REDACTED]"

# Characters allowed in a cassette filename; everything else becomes "_".
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")

Scrubber = Callable[[str], str]

# Secrets that may end up in a *request body* (e.g. a prompt that pastes an API
# key or password).  Applied to the request content before it is written, so
# the on-disk corpus stays shareable.  Order matters: more specific patterns
# (anthropic) run before the broader sk- rule.
DEFAULT_SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"), "[REDACTED-ANTHROPIC-KEY]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "[REDACTED-OPENAI-KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED-AWS-KEY]"),
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
    """Redact known secret shapes from *text*."""
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
    interaction: CapturedInteraction, *, scrub: Optional[Scrubber] = None
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
        "chunks": [
            {"data": _encode_blob(c.data), "timestamp_offset": c.timestamp_offset}
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
    fall back to base64.  By default known secret shapes are scrubbed from the
    request body before writing — pass ``scrub_request_body=False`` to disable,
    or ``secret_patterns=[...]`` to supply your own.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        scrub_request_body: bool = True,
        secret_patterns: Optional[List[Tuple[re.Pattern, str]]] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if scrub_request_body:
            self._scrub: Optional[Scrubber] = lambda t: scrub_secrets(t, secret_patterns)
        else:
            self._scrub = None

    def _path(self, interaction_id: str) -> Path:
        # Sanitize anything that could escape the corpus dir or trip up a
        # filesystem: path separators, colons (NTFS streams / drive-relative
        # paths on Windows) and other reserved characters.
        safe = _UNSAFE_FILENAME_CHARS.sub("_", interaction_id) or "x"
        return self.root / f"{safe}.json"

    async def save(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        path = self._path(interaction_id)
        text = json.dumps(
            _interaction_to_dict(interaction, scrub=self._scrub),
            indent=2,
            ensure_ascii=False,
        )
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    async def load(self, interaction_id: str) -> CapturedInteraction:
        path = self._path(interaction_id)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise KeyError(
                f"No recorded interaction for id={interaction_id!r} in {self.root}. "
                "Run the record phase before replaying."
            ) from None
        return _interaction_from_dict(json.loads(text))

    def __contains__(self, interaction_id: str) -> bool:
        return self._path(interaction_id).exists()

    async def has(self, interaction_id: str) -> bool:
        return self._path(interaction_id).exists()

    async def discard(self, interaction_id: str) -> None:
        try:
            self._path(interaction_id).unlink()
        except FileNotFoundError:
            pass

    def ids(self) -> List[str]:
        """Sorted interaction ids currently on disk."""
        return sorted(p.stem for p in self.root.glob("*.json"))

    def __len__(self) -> int:
        return sum(1 for _ in self.root.glob("*.json"))
