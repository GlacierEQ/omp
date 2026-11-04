"""SDK exceptions."""

from __future__ import annotations


class SDKError(Exception):
    """Base SDK error."""


class PolicyError(SDKError):
    """Raised when a policy decision blocks an operation."""


class VerificationError(SDKError):
    """Raised when independent verification fails or is missing."""


class QualityError(SDKError):
    """Raised when a quality gate fails."""


class ReceiptError(SDKError):
    """Raised when a receipt cannot be sealed or verified."""


class AdapterError(SDKError):
    """Raised when an injected adapter fails."""


class ConfigurationError(SDKError):
    """Raised when SDK configuration is invalid."""
