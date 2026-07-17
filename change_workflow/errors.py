class ChangeWorkflowError(Exception):
    """Base workflow error safe for adapter translation."""


class ChangeNotFoundError(ChangeWorkflowError):
    pass


class InvalidTransitionError(ChangeWorkflowError):
    pass


class ConcurrencyError(ChangeWorkflowError):
    pass
