"""
Storage-agnostic data structures for a captured HTTP interaction.

Storage backends (the JSON-cassette FileStore today, others later) consume
CapturedInteraction without the transports knowing about them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class CapturedChunk:
    """One raw byte frame from an HTTP response body."""

    data: bytes
    # Seconds elapsed since the first chunk arrived.  Stored so replay can
    # optionally simulate realistic pacing; instant replay ignores it.
    timestamp_offset: float = 0.0


@dataclass
class CapturedRequest:
    method: str
    url: str
    # Raw (bytes, bytes) header pairs — provider-neutral, no decoding here.
    headers: List[Tuple[bytes, bytes]]
    content: bytes


@dataclass
class CapturedInteraction:
    """Complete record of one request/response exchange."""

    request: CapturedRequest
    response_status: int
    response_headers: List[Tuple[bytes, bytes]]
    # extensions minus transport-specific keys like "network_stream"
    response_extensions: dict
    chunks: List[CapturedChunk] = field(default_factory=list)
    # Provenance for the corpus: provider, model, semantic_key, recorded_at.
    # Free-form so new fields (e.g. a future migration-report needs) drop in
    # without a schema change.  Populated by RecordingTransport; empty when an
    # interaction is hand-built or loaded from a pre-metadata cassette.
    metadata: Dict[str, Any] = field(default_factory=dict)
