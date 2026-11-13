"""OpenAI adapter, using the official `openai` SDK (Responses API with structured output)."""

import json
from typing import Any

import openai
from pydantic import BaseModel

from operon.modules.ai.provider import (
    ProviderError,
    StructuredResult,
    ToolCall,
    ToolResult,
    ToolSpec,
    ToolTurn,
)


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
            response: Any = await self._client.responses.create(
                model=self.model,
                instructions=system,
                input=transcript,
                tools=[
                    {
                        "type": "function",
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                        "strict": False,
                    }
                    for t in tools
                ],
                max_output_tokens=max_output_tokens,
            )
        except (openai.RateLimitError, openai.APIConnectionError) as exc:
            raise ProviderError(type(exc).__name__, retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                f"{type(exc).__name__} ({exc.status_code})", retryable=exc.status_code >= 500
            ) from exc
        usage = response.usage
        tokens = (int(usage.input_tokens), int(usage.output_tokens)) if usage else (0, 0)
        served_by = str(getattr(response, "model", None) or self.model)
        output = list(response.output or [])
        refusal = _refusal(response)
        if refusal:
            return ToolTurn(None, [], "refused", served_by, *tokens, output, refusal[:200])
        calls = []
        for item in output:
            if getattr(item, "type", None) == "function_call":
                try:
                    args = json.loads(item.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_invalid_json": item.arguments}
                calls.append(ToolCall(item.call_id, item.name, args))
        if getattr(response, "status", None) == "incomplete" and not calls:
            return ToolTurn(
                response.output_text or None, [], "truncated", served_by, *tokens, output
            )
        text = response.output_text or None
        return ToolTurn(text, calls, "tool_use" if calls else "end", served_by, *tokens, output)

    def extend(self, transcript: list[Any], turn: ToolTurn, results: list[ToolResult]) -> None:
        # Reasoning and function-call items are echoed back as returned.
        transcript.extend(turn.raw or [])
        transcript.extend(
            {"type": "function_call_output", "call_id": r.call_id, "output": r.content}
            for r in results
        )


def _refusal(response: Any) -> str | None:
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return str(getattr(part, "refusal", "refused"))
    return None
