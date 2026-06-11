from importlib.metadata import PackageNotFoundError, version as _version

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest
from .comparators import (
    Comparator,
    ComparisonResult,
    EmbeddingComparator,
    ExactMatchComparator,
    FuzzyComparator,
    JudgeComparator,
    build_comparators,
)
from .keying import Fingerprint, default_key, fingerprint, fingerprint_of
from .migration import (
    CategoryBreakdown,
    MigrationReport,
    RowResult,
    TokenTotals,
    annotate_corpus,
    migration_id_for,
    run_migration,
)
from .providers import (
    Conversation,
    DecodedResponse,
    DecodeError,
    MissingAPIKeyError,
    ProviderAdapter,
    UnsupportedRequestError,
    conversation_of,
    decode_interaction,
)
from .report import render_console, render_html, render_markdown
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
    "fingerprint_of",
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
    # Providers
    "Conversation",
    "DecodedResponse",
    "DecodeError",
    "MissingAPIKeyError",
    "ProviderAdapter",
    "UnsupportedRequestError",
    "conversation_of",
    "decode_interaction",
    # Comparators
    "Comparator",
    "ComparisonResult",
    "ExactMatchComparator",
    "FuzzyComparator",
    "EmbeddingComparator",
    "JudgeComparator",
    "build_comparators",
    # Migration report
    "CategoryBreakdown",
    "MigrationReport",
    "RowResult",
    "TokenTotals",
    "annotate_corpus",
    "migration_id_for",
    "run_migration",
    "render_console",
    "render_html",
    "render_markdown",
]
