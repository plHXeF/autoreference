from __future__ import annotations

from typing import Protocol

from autoreference.models import ReferenceCandidate


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[ReferenceCandidate]: ...

    async def close(self) -> None: ...


class ProviderError(RuntimeError):
    """A provider failed without invalidating results from other providers."""

    def __init__(self, message: str, *, code: str = "request_failed") -> None:
        super().__init__(message)
        self.code = code
