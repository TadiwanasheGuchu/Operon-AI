"""OpenAI adapter, using the official `openai` SDK (Responses API with structured output)."""

from typing import Any

import openai
from pydantic import BaseModel

from operon.modules.ai.provider import ProviderError, StructuredResult


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self.model = model
        self._client = openai.AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=2)

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_output_tokens: int
    ) -> StructuredResult[T]:
        try:
            response: Any = await self._client.responses.parse(
                model=self.model,
                instructions=system,
                input=user,
                text_format=schema,
                max_output_tokens=max_output_tokens,
            )
        except (openai.RateLimitError, openai.APIConnectionError) as exc:
            raise ProviderError(type(exc).__name__, retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                f"{type(exc).__name__} ({exc.status_code})", retryable=exc.status_code >= 500
            ) from exc
        except (openai.LengthFinishReasonError, openai.ContentFilterFinishReasonError) as exc:
            return StructuredResult(None, self.model, 0, 0, "truncated", type(exc).__name__)

        usage = response.usage
        tokens = (int(usage.input_tokens), int(usage.output_tokens)) if usage else (0, 0)
        served_by = str(getattr(response, "model", None) or self.model)
        if getattr(response, "status", None) == "incomplete":
            return StructuredResult(None, served_by, *tokens, "truncated")
        refusal = _refusal(response)
        if refusal:
            return StructuredResult(None, served_by, *tokens, "refused", refusal[:200])
        parsed = response.output_parsed
        if parsed is None:
            return StructuredResult(None, served_by, *tokens, "invalid")
        return StructuredResult(parsed, served_by, *tokens, "ok")


def _refusal(response: Any) -> str | None:
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return str(getattr(part, "refusal", "refused"))
    return None
