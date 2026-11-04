"""GlacierEQ SDK — capability + quality integration package."""

from __future__ import annotations

from .errors import SDKError, PolicyError, VerificationError, QualityError
from .capability import CapabilityClient
from .runtime import ConnectorRuntimeClient
from .receipts import ReceiptStore, ReceiptError
from .quality import QualityGate, EvidenceChain, QUALITY_THRESHOLD
from .client import GlaciereqSDK

__all__ = [
    "SDKError",
    "PolicyError",
    "VerificationError",
    "QualityError",
    "CapabilityClient",
    "ConnectorRuntimeClient",
    "ReceiptStore",
    "ReceiptError",
    "QualityGate",
    "EvidenceChain",
    "QUALITY_THRESHOLD",
    "GlaciereqSDK",
]

__version__ = "1.0.0"
