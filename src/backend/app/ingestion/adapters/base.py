"""Format adapter base class and shared types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ContentChunk:
    """A unit of extracted text with structural context."""

    chunk_id: str
    text: str
    structural_context: dict
    order: int


@dataclass
class ExtractionResult:
    """Output of a format adapter."""

    chunks: list[ContentChunk] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class FormatAdapter(ABC):
    """Contract for all format adapters."""

    @abstractmethod
    def can_handle(self, filename: str, content_type: str | None) -> bool:
        """Return True if this adapter handles the given format."""
        ...

    @abstractmethod
    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text content from raw file bytes."""
        ...
