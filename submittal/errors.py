class SubmittalError(Exception):
    pass


class SubmittalNotFoundError(SubmittalError):
    pass


class SubmittalTransitionError(SubmittalError):
    pass


class SubmittalValidationError(SubmittalError):
    pass


class SubmittalConcurrencyError(SubmittalError):
    pass


class SubmittalPersistenceError(SubmittalError):
    pass


class AttachmentIngestionError(SubmittalError):
    pass


class AttachmentSecurityError(AttachmentIngestionError):
    pass


class AttachmentUnsupportedError(AttachmentIngestionError):
    pass
