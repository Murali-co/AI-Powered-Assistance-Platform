"""
No-Op ChromaDB telemetry provider to prevent telemetry errors and protect user privacy.
"""
import chromadb
from chromadb.telemetry.product import ProductTelemetryClient
from chromadb.telemetry.product.events import ProductTelemetryEvent
from overrides import override

class NoOpTelemetry(ProductTelemetryClient):
    """
    Safe no-op telemetry client that satisfies ChromaDB's Component system
    without sending any external HTTP requests to PostHog or any other provider.
    """
    def __init__(self, system):
        super().__init__(system)

    @override
    def capture(self, event: ProductTelemetryEvent) -> None:
        pass
