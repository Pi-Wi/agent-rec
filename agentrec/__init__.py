from importlib.metadata import PackageNotFoundError, version as _version

from .capture import CapturedChunk, CapturedInteraction, CapturedRequest
from .comparators import (
    DEFAULT_JUDGE_MODEL,
    Comparator,
    ComparisonResult,
    EmbeddingComparator,
    ExactMatchComparator,
    FuzzyComparator,
    JsonComparator,
    JudgeComparator,
    ParsedComparator,
    ToolCallsComparator,
    build_comparators,
    parse_compare_spec,
)
from .importers import (
    IMPORT_PREFIX,
    ImportSourceError,
    ImportSummary,
    import_corpus,
)
from .keying import (
    SEMANTIC_KEY_VERSION,
    Fingerprint,
    default_key,
    fingerprint,
    fingerprint_of,
)
from .migration import (
    CategoryBreakdown,
    GateResult,
    LatencyStats,
    MigrationReport,
    RowResult,
    TokenTotals,
    annotate_corpus,
    migration_id_for,
    run_migration,
)
from .pricing import (
    CostEstimate,
    CostTotals,
    PricingCatalog,
    PricingError,
    PricingProfile,
    PricingSnapshot,
    RateRef,
    ReportPricing,
    ResolvedRate,
    RowCost,
    price_report,
)
from .providers import (
    Conversation,
    DecodedResponse,
    DecodeError,
    MissingAPIKeyError,
    ProviderAdapter,
    TokenUsage,
    ToolCall,
    UnsupportedRequestError,
    adapter_for_host,
    adapter_for_model,
    adapter_for_provider,
    conversation_of,
    decode_interaction,
    register,
    render_response,
    usage_of,
)
from .report import render_console, render_html, render_markdown
from .session import (
    DynamicTransport,
    SyncDynamicTransport,
    async_client,
    cassette,
    sync_client,
)
from .store import (
    DEFAULT_SECRET_PATTERNS,
    FileStore,
    InMemoryStore,
    InteractionStore,
    scrub_secrets,
)
from .transport import (
    AutoTransport,
    RecordingTransport,
    ReplayTransport,
    SyncAutoTransport,
    SyncRecordingTransport,
    SyncReplayTransport,
)

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
    "SEMANTIC_KEY_VERSION",
    "default_key",
    "fingerprint",
    "fingerprint_of",
    # Stores
    "FileStore",
    "InMemoryStore",
    "InteractionStore",
    "DEFAULT_SECRET_PATTERNS",
    "scrub_secrets",
    # Low-level transports
    "AutoTransport",
    "RecordingTransport",
    "ReplayTransport",
    "SyncAutoTransport",
    "SyncRecordingTransport",
    "SyncReplayTransport",
    # High-level facade
    "DynamicTransport",
    "SyncDynamicTransport",
    "async_client",
    "sync_client",
    "cassette",
    # Providers
    "Conversation",
    "DecodedResponse",
    "DecodeError",
    "MissingAPIKeyError",
    "ProviderAdapter",
    "TokenUsage",
    "ToolCall",
    "UnsupportedRequestError",
    "adapter_for_host",
    "adapter_for_model",
    "adapter_for_provider",
    "conversation_of",
    "decode_interaction",
    "register",
    "render_response",
    "usage_of",
    # Pricing (derived cost estimates)
    "CostEstimate",
    "CostTotals",
    "PricingCatalog",
    "PricingError",
    "PricingProfile",
    "PricingSnapshot",
    "RateRef",
    "ReportPricing",
    "ResolvedRate",
    "RowCost",
    "price_report",
    # Comparators
    "DEFAULT_JUDGE_MODEL",
    "Comparator",
    "ComparisonResult",
    "ExactMatchComparator",
    "FuzzyComparator",
    "JsonComparator",
    "ToolCallsComparator",
    "EmbeddingComparator",
    "JudgeComparator",
    "ParsedComparator",
    "build_comparators",
    "parse_compare_spec",
    # Migration report
    "CategoryBreakdown",
    "GateResult",
    "LatencyStats",
    "MigrationReport",
    "RowResult",
    "TokenTotals",
    "annotate_corpus",
    "migration_id_for",
    "run_migration",
    # Corpus importers (observability exports → synthesized cassettes)
    "IMPORT_PREFIX",
    "ImportSourceError",
    "ImportSummary",
    "import_corpus",
    "render_console",
    "render_html",
    "render_markdown",
]
