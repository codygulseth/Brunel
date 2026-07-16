"""User-facing errors raised by Brunel's ingestion boundary."""


class IngestionError(Exception):
    """Base error for an ingestion job that cannot complete."""


class SourceFileNotFoundError(IngestionError):
    """The requested local source file does not exist."""


class UnsupportedFileTypeError(IngestionError):
    """No registered extractor supports the source file type."""


class EmptyDocumentError(IngestionError):
    """A text-based source contains no extractable content."""


class DocumentExtractionError(IngestionError):
    """The source container cannot be opened or interpreted."""
