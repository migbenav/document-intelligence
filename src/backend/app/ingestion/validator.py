"""Document validation: format, size, encoding checks."""

from dataclasses import dataclass
from pathlib import Path

from app.models.document import DocumentFormat

# Size limits in bytes
_MAX_SIZE_TEXT = 1_048_576  # 1 MB for .md and .txt
_MAX_SIZE_PDF = 10_485_760  # 10 MB for .pdf

# Extension to format mapping
_EXTENSION_MAP: dict[str, DocumentFormat] = {
    ".md": DocumentFormat.MARKDOWN,
    ".txt": DocumentFormat.PLAIN_TEXT,
    ".pdf": DocumentFormat.PDF,
}

_SUPPORTED_EXTENSIONS = list(_EXTENSION_MAP.keys())


@dataclass
class ValidationResult:
    """Result of file validation."""

    valid: bool
    error_code: str | None = None
    error_message: str | None = None
    detected_format: DocumentFormat | None = None


class Validator:
    """Validates uploaded files for format, size, and encoding requirements."""

    def validate(self, file_bytes: bytes, filename: str) -> ValidationResult:
        """Validate a file's format, size, and encoding.

        Args:
            file_bytes: Raw bytes of the uploaded file.
            filename: Original filename including extension.

        Returns:
            ValidationResult indicating success or failure with details.
        """
        # 1. Check supported extension
        extension = Path(filename).suffix.lower()

        if extension not in _EXTENSION_MAP:
            supported = ", ".join(_SUPPORTED_EXTENSIONS)
            return ValidationResult(
                valid=False,
                error_code="unsupported_format",
                error_message=(
                    f"File format '{extension or '(none)'}' is not supported. "
                    f"Please upload a file with one of these extensions: {supported}"
                ),
            )

        detected_format = _EXTENSION_MAP[extension]
        file_size = len(file_bytes)

        # 2. Check size limits
        if extension in (".md", ".txt"):
            max_size = _MAX_SIZE_TEXT
        else:
            max_size = _MAX_SIZE_PDF

        if file_size > max_size:
            max_mb = max_size / 1_048_576
            return ValidationResult(
                valid=False,
                error_code="file_too_large",
                error_message=(
                    f"File exceeds the maximum allowed size of {max_mb:.0f} MB "
                    f"for {extension} files. Please reduce the file size and try again."
                ),
            )

        # 3. Check UTF-8 encoding for text-based formats
        if extension in (".md", ".txt"):
            try:
                file_bytes.decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                return ValidationResult(
                    valid=False,
                    error_code="invalid_encoding",
                    error_message=(
                        "File is not valid UTF-8 encoded text. "
                        "Please save the file with UTF-8 encoding and try again."
                    ),
                )

        return ValidationResult(
            valid=True,
            detected_format=detected_format,
        )
