class RFIError(Exception):
    pass


class RFINotFoundError(RFIError):
    pass


class RFITransitionError(RFIError):
    pass


class RFIDraftingError(RFIError):
    pass


class RFIConcurrencyError(RFIError):
    pass


class RFIPersistenceError(RFIError):
    pass
