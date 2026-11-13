"""The interface every model provider implements (ADR 0006).

Callers ask for a structured output (a Pydantic model) and get back either a validated
instance or a reason there isn't one. Vendor SDKs are imported only by the adapter modules.
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    output: T | None
    model: str  # the model that actually served the request
    input_tokens: int
    output_tokens: int
    # "ok" | "refused" | "invalid" (no parseable output) | "truncated"
    outcome: str
    detail: str | None = None


class ProviderError(Exception):
    """The provider couldn't be reached or rejected the request. Never shown verbatim to users."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_output_tokens: int
    ) -> StructuredResult[T]: ...
