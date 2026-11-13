"""The interface every model provider implements (ADR 0006).

Callers ask for a structured output (a Pydantic model) and get back either a validated
instance or a reason there isn't one. Vendor SDKs are imported only by the adapter modules.
"""

from dataclasses import dataclass
from typing import Any, Protocol

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


# --- tool use (assistant and agents, ADR 0014) ---------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolTurn:
    """One model response in a tool loop."""

    text: str | None
    tool_calls: list[ToolCall]
    # "tool_use" (calls to run) | "end" (final text) | "refused" | "truncated"
    outcome: str
    model: str
    input_tokens: int
    output_tokens: int
    # Provider-native assistant content, echoed back verbatim (keeps thinking blocks intact).
    raw: Any = None
    detail: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False


class ToolLoopProvider(Protocol):
    """A provider that can run a multi-step tool loop. The transcript is provider-native and
    opaque to callers; they only start it, ask for the next turn and add tool results."""

    name: str
    model: str

    def start(self, history: list[tuple[str, str]], user_text: str) -> list[Any]: ...

    async def converse(
        self,
        *,
        system: str,
        transcript: list[Any],
        tools: list[ToolSpec],
        max_output_tokens: int,
    ) -> ToolTurn: ...

    def extend(self, transcript: list[Any], turn: ToolTurn, results: list[ToolResult]) -> None: ...
