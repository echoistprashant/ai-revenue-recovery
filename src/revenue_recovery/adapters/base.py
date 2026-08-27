from abc import ABC, abstractmethod
from typing import Any

from revenue_recovery.models import PaymentEventCreate


class BaseGatewayAdapter(ABC):
    """Abstract interface for payment gateway adapters."""

    @abstractmethod
    def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify the cryptographic signature of an incoming gateway webhook payload."""
        pass

    @abstractmethod
    def normalize_event(self, payload: dict[str, Any]) -> PaymentEventCreate:
        """Normalize a provider-specific webhook payload into internal PaymentEventCreate model."""
        pass
