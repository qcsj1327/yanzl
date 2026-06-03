class FuturesMvpError(Exception):
    """Base error for the futures MVP skeleton."""


class DecimalRequiredError(FuturesMvpError, TypeError):
    """Raised when a float is passed where Decimal is required."""


class DuplicateEventError(FuturesMvpError):
    """Raised when an already processed external event is observed."""
