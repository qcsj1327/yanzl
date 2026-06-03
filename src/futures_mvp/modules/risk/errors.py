class RiskError(Exception):
    """Base error for pure risk engine failures."""


class RiskConfigurationError(RiskError):
    """Raised when pure risk configuration is incomplete or invalid."""
