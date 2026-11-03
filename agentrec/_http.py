"""The HTTP client library agentrec builds on: ``httpx2`` when present, else ``httpx``.

The official OpenAI (2.47+) and Anthropic (1.0+) SDKs moved to ``httpx2`` and
reject an ``http_client`` built from ``httpx``, while older SDKs require the
reverse. A client from ``agentrec.async_client()`` has to match whichever SDK it
is handed to, so the library is resolved once here and every module imports it
from this file. Mixing the two would fail on ``isinstance`` checks and on
exception classes that look identical but are unrelated.

``httpx2`` is not a dependency: an SDK that needs it brings it along, which is
exactly the case where it should win. If one environment holds both a new and an
old SDK, set ``AGENTREC_HTTP_BACKEND`` to ``httpx`` or ``httpx2`` to choose.
"""
from __future__ import annotations

import importlib
import os

_VALID = ("httpx", "httpx2")
_requested = os.environ.get("AGENTREC_HTTP_BACKEND", "").strip().lower()

if _requested and _requested not in _VALID:
    raise ImportError(
        f"AGENTREC_HTTP_BACKEND must be one of {_VALID}, got {_requested!r}"
    )

if _requested:
    httpx = importlib.import_module(_requested)
else:
    try:
        httpx = importlib.import_module("httpx2")
    except ImportError:
        httpx = importlib.import_module("httpx")

BACKEND = httpx.__name__

__all__ = ["BACKEND", "httpx"]
