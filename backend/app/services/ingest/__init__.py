"""Job-source connectors and the registry that resolves them by source type."""

from __future__ import annotations

from app.models.enums import SourceType
from app.services.ingest.ashby import AshbyClient
from app.services.ingest.base import RawJob, SourceClient
from app.services.ingest.greenhouse import GreenhouseClient
from app.services.ingest.http import HttpFetcher, HttpxFetcher
from app.services.ingest.lever import LeverClient
from app.services.ingest.verifier import JobVerifier, VerificationResult

CLIENT_REGISTRY: dict[str, type] = {
    SourceType.GREENHOUSE.value: GreenhouseClient,
    SourceType.LEVER.value: LeverClient,
    SourceType.ASHBY.value: AshbyClient,
}


def get_client(source_type: str, fetcher: HttpFetcher | None = None) -> SourceClient:
    """Resolve the connector for a source type."""
    try:
        client_class = CLIENT_REGISTRY[source_type]
    except KeyError as exc:
        raise ValueError(
            f"No connector for source type {source_type!r}. "
            f"Supported: {', '.join(sorted(CLIENT_REGISTRY))}."
        ) from exc
    return client_class(fetcher=fetcher)


__all__ = [
    "AshbyClient",
    "CLIENT_REGISTRY",
    "GreenhouseClient",
    "HttpFetcher",
    "HttpxFetcher",
    "JobVerifier",
    "LeverClient",
    "RawJob",
    "SourceClient",
    "VerificationResult",
    "get_client",
]
