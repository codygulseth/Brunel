"""Safe failure types for retrieval and answer generation."""


class CitedQAError(Exception):
    """Base cited-QA error."""


class AnswerProviderError(CitedQAError):
    """The configured answer provider could not return a usable answer."""


class InvalidStructuredOutputError(AnswerProviderError):
    """A model provider repeatedly returned output that failed validation."""


class CitationValidationError(CitedQAError):
    """A provider cited evidence that was not supplied by retrieval."""
