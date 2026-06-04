"""
Storage-agnostic data structures for a captured HTTP interaction.

Both the cassette (YAML) and corpus (Parquet) serialisers will consume
CapturedInteraction without knowing about each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class CapturedChunk:
    """One raw byte frame from a streaming response body."""

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
    """Complete record of one request/streaming-response exchange."""

    request: CapturedRequest
    response_status: int
    response_headers: List[Tuple[bytes, bytes]]
    # extensions minus transport-specific keys like "network_stream"
    response_extensions: dict
    chunks: List[CapturedChunk] = field(default_factory=list)
