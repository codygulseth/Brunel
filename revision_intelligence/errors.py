class RevisionIntelligenceError(Exception):
    """Base error for safe comparison failures."""


class DocumentNotFoundError(RevisionIntelligenceError):
    pass


class CrossProjectComparisonError(RevisionIntelligenceError):
    pass


class DocumentsNotComparableError(RevisionIntelligenceError):
    pass


class InsufficientContentError(RevisionIntelligenceError):
    pass
