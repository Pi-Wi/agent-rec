from importlib.metadata import PackageNotFoundError, version as _version

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest
from .keying import Fingerprint, default_key, fingerprint
from .session import DynamicTransport, async_client, cassette
from .store import FileStore, InMemoryStore, InteractionStore
from .transport import AutoTransport, RecordingTransport, ReplayTransport

try:
    __version__ = _version("agentrec")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0.dev0"

__all__ = [
    "__version__",
    # Data
    "CapturedChunk",
    "CapturedInteraction",
    "CapturedRequest",
    # Keying
    "Fingerprint",
    "default_key",
    "fingerprint",
    # Stores
    "FileStore",
    "InMemoryStore",
    "InteractionStore",
    # Low-level transports
    "AutoTransport",
    "RecordingTransport",
    "ReplayTransport",
    # High-level facade
    "DynamicTransport",
    "async_client",
    "cassette",
]
