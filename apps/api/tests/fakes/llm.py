"""A scripted tool-loop provider: plays the model's part, deterministically.

Each script entry is either a list of tool calls `[("tool_name", {...}), ...]`, a final answer
string, or a callable that receives the transcript so far and returns one of those (to answer
with figures the tools actually returned). Token counts per turn are configurable.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from operon.modules.ai.provider import ToolCall, ToolResult, ToolSpec, ToolTurn

Step = list[tuple[str, dict[str, Any]]] | str | Callable[[list[Any]], Any]


@dataclass
class ScriptedLLM:
    script: list[Step]
    name: str = "anthropic"
    model: str = "scripted-model"
    tokens_per_turn: tuple[int, int] = (500, 100)
    repeat_last: bool = False
    seen_tools: list[list[str]] = field(default_factory=list)
    seen_systems: list[str] = field(default_factory=list)
    turns: int = 0

    def start(self, history: list[tuple[str, str]], user_text: str) -> list[Any]:
        return [
            *({"role": r, "content": t} for r, t in history),
            {"role": "user", "content": user_text},
        ]

    async def converse(
        self, *, system: str, transcript: list[Any], tools: list[ToolSpec], max_output_tokens: int
    ) -> ToolTurn:
        self.seen_tools.append([t.name for t in tools])
        self.seen_systems.append(system)
        index = min(self.turns, len(self.script) - 1) if self.repeat_last else self.turns
        step = self.script[index]
        self.turns += 1
        if callable(step):
            step = step(transcript)
        if isinstance(step, str):
            return ToolTurn(step, [], "end", self.model, *self.tokens_per_turn, raw=step)
        calls = [ToolCall(f"call_{self.turns}_{i}", n, inp) for i, (n, inp) in enumerate(step)]
        return ToolTurn(None, calls, "tool_use", self.model, *self.tokens_per_turn, raw=calls)

    def extend(self, transcript: list[Any], turn: ToolTurn, results: list[ToolResult]) -> None:
        transcript.append(
            {"role": "assistant", "calls": [(c.name, c.input) for c in turn.tool_calls]}
        )
        transcript.append({"role": "tool", "results": [(r.content, r.is_error) for r in results]})

    @staticmethod
    def last_results(transcript: list[Any]) -> list[tuple[Any, bool]]:
        """Parsed outputs of the most recent tool results (errors as plain strings)."""
        for entry in reversed(transcript):
            if entry.get("role") == "tool":
                out = []
                for content, is_error in entry["results"]:
                    out.append((content if is_error else json.loads(content), is_error))
                return out
        return []
