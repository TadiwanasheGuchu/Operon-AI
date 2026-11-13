"""Anthropic adapter, using the official `anthropic` SDK.

- Structured output via `messages.parse(output_format=...)`; the SDK validates against the schema.
- Effort "low": explanations are short rewrites of numbers already computed in code.
- Server-side refusal fallbacks are enabled (`fallbacks="default"`): if the model declines, the
  API re-runs the request on Anthropic's recommended fallback model within the same call. The
  model that served the request is recorded either way.
"""

from typing import Any

import anthropic
from pydantic import BaseModel

from operon.modules.ai.provider import (
    ProviderError,
    StructuredResult,
    ToolCall,
    ToolResult,
    ToolSpec,
    ToolTurn,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_output_tokens: int
    ) -> StructuredResult[T]:
        try:
            response: Any = await self._client.beta.messages.parse(
                model=self.model,
                max_tokens=max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": "low"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            raise ProviderError(type(exc).__name__, retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"{type(exc).__name__} ({exc.status_code})", retryable=exc.status_code >= 500
            ) from exc

        usage = response.usage
        served_by = str(getattr(response, "model", None) or self.model)
        tokens = (int(usage.input_tokens or 0), int(usage.output_tokens or 0))
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            return StructuredResult(None, served_by, *tokens, "refused", category)
        if response.stop_reason == "max_tokens":
            return StructuredResult(None, served_by, *tokens, "truncated")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            return StructuredResult(None, served_by, *tokens, "invalid")
        return StructuredResult(parsed, served_by, *tokens, "ok")

    # --- tool loop ---------------------------------------------------------------------------

    def start(self, history: list[tuple[str, str]], user_text: str) -> list[Any]:
        transcript: list[Any] = [{"role": r, "content": t} for r, t in history]
        transcript.append({"role": "user", "content": user_text})
        return transcript

    async def converse(
        self,
        *,
        system: str,
        transcript: list[Any],
        tools: list[ToolSpec],
        max_output_tokens: int,
    ) -> ToolTurn:
        try:
            response: Any = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=max_output_tokens,
                system=system,
                messages=transcript,
                tools=[
                    {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                    for t in tools
                ],
                output_config={"effort": "medium"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            raise ProviderError(type(exc).__name__, retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"{type(exc).__name__} ({exc.status_code})", retryable=exc.status_code >= 500
            ) from exc
        usage = response.usage
        served_by = str(getattr(response, "model", None) or self.model)
        tokens = (int(usage.input_tokens or 0), int(usage.output_tokens or 0))
        text = "".join(b.text for b in response.content if b.type == "text") or None
        calls = [
            ToolCall(b.id, b.name, dict(b.input or {}))
            for b in response.content
            if b.type == "tool_use"
        ]
        if response.stop_reason == "refusal":
            return ToolTurn(None, [], "refused", served_by, *tokens, response.content)
        if response.stop_reason == "max_tokens":
            return ToolTurn(text, [], "truncated", served_by, *tokens, response.content)
        outcome = "tool_use" if calls else "end"
        return ToolTurn(text, calls, outcome, served_by, *tokens, response.content)

    def extend(self, transcript: list[Any], turn: ToolTurn, results: list[ToolResult]) -> None:
        transcript.append({"role": "assistant", "content": turn.raw})
        transcript.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in results
                ],
            }
        )
