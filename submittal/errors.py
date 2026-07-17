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
