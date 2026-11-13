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

from operon.modules.ai.provider import ProviderError, StructuredResult

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
