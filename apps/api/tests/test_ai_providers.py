"""Provider adapters: request shape and outcome mapping, with the SDK call replaced.

No network: live calls need provider keys, which are not configured in this environment.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from operon.core.config import Settings
from operon.modules.ai.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from operon.modules.ai.openai_provider import OpenAIProvider
from operon.modules.ai.provider import ToolResult, ToolSpec
from operon.modules.ai.service import ProviderRegistry
from operon.modules.intelligence.explain import Explanation

OUT = Explanation(what_happened="x" * 25, why_it_matters="y" * 25)


class Recorder:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    async def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def anthropic_response(stop: str, parsed: Any = OUT) -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        stop_details=SimpleNamespace(category="cyber") if stop == "refusal" else None,
        parsed_output=parsed,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=321, output_tokens=54),
    )


async def test_anthropic_request_uses_structured_output_low_effort_and_fallbacks() -> None:
    p = AnthropicProvider(api_key="test", model="claude-opus-5-5", timeout=5)
    rec = Recorder(anthropic_response("end_turn"))
    p._client.beta.messages.parse = rec  # type: ignore[method-assign]
    result = await p.generate(system="s", user="u", schema=Explanation, max_output_tokens=4000)
    assert result.outcome == "ok"
    assert result.output == OUT
    assert (result.input_tokens, result.output_tokens) == (321, 54)
    kw = rec.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_format"] is Explanation
    assert kw["output_config"] == {"effort": "low"}
    assert kw["betas"] == [FALLBACK_BETA]
    assert kw["fallbacks"] == "default"
    assert "thinking" not in kw  # always on for this model; never disabled


@pytest.mark.parametrize(
    ("stop", "parsed", "outcome"),
    [
        ("refusal", None, "refused"),
        ("max_tokens", None, "truncated"),
        ("end_turn", None, "invalid"),
    ],
)
async def test_anthropic_outcomes(stop: str, parsed: Any, outcome: str) -> None:
    p = AnthropicProvider(api_key="test", model="claude-opus-5-5", timeout=5)
    p._client.beta.messages.parse = Recorder(anthropic_response(stop, parsed))  # type: ignore[method-assign]
    result = await p.generate(system="s", user="u", schema=Explanation, max_output_tokens=10)
    assert result.outcome == outcome
    assert result.output is None


async def test_openai_request_and_refusal() -> None:
    p = OpenAIProvider(api_key="test", model="configured-model", timeout=5)
    ok = SimpleNamespace(
        status="completed",
        output=[],
        output_parsed=OUT,
        model="configured-model",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    rec = Recorder(ok)
    p._client.responses.parse = rec  # type: ignore[method-assign]
    result = await p.generate(system="s", user="u", schema=Explanation, max_output_tokens=99)
    assert result.outcome == "ok"
    assert rec.kwargs["text_format"] is Explanation
    assert rec.kwargs["instructions"] == "s"
    refused = SimpleNamespace(
        status="completed",
        output=[SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="no")])],
        output_parsed=None,
        model="configured-model",
        usage=None,
    )
    p._client.responses.parse = Recorder(refused)  # type: ignore[method-assign]
    result = await p.generate(system="s", user="u", schema=Explanation, max_output_tokens=99)
    assert result.outcome == "refused"


def test_registry_only_offers_configured_providers() -> None:
    assert ProviderRegistry.from_settings(Settings(environment="test")).providers == {}
    with_keys = ProviderRegistry.from_settings(
        Settings(
            environment="test", anthropic_api_key=SecretStr("k"), openai_api_key=SecretStr("k")
        )
    )
    # OpenAI needs an explicitly chosen model as well as a key.
    assert sorted(with_keys.providers) == ["anthropic"]


# --- tool loops --------------------------------------------------------------------------------

TOOLS_SPEC = [ToolSpec("list_insights", "List insights.", {"type": "object", "properties": {}})]


async def test_anthropic_tool_loop_echoes_content_and_maps_tool_calls() -> None:
    p = AnthropicProvider(api_key="test", model="claude-opus-5-5", timeout=5)
    content = [
        SimpleNamespace(type="thinking", thinking="…", signature="sig"),
        SimpleNamespace(type="tool_use", id="toolu_1", name="list_insights", input={"limit": 3}),
    ]
    rec = Recorder(
        SimpleNamespace(
            stop_reason="tool_use",
            content=content,
            model="claude-opus-5-5",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
    )
    p._client.beta.messages.create = rec  # type: ignore[method-assign]
    transcript = p.start([("user", "earlier"), ("assistant", "answer")], "What's urgent?")
    turn = await p.converse(
        system="s", transcript=transcript, tools=TOOLS_SPEC, max_output_tokens=99
    )
    assert (turn.outcome, turn.tool_calls[0].name, turn.tool_calls[0].input) == (
        "tool_use",
        "list_insights",
        {"limit": 3},
    )
    assert rec.kwargs["tools"][0]["input_schema"] == {"type": "object", "properties": {}}
    assert rec.kwargs["fallbacks"] == "default"
    assert "tool_choice" not in rec.kwargs
    p.extend(transcript, turn, [ToolResult("toolu_1", '{"insights": []}')])
    # The assistant turn is echoed verbatim (thinking blocks intact), then the tool results.
    assert transcript[-2] == {"role": "assistant", "content": content}
    assert transcript[-1]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": '{"insights": []}',
        "is_error": False,
    }


async def test_openai_tool_loop_maps_function_calls() -> None:
    p = OpenAIProvider(api_key="test", model="configured-model", timeout=5)
    items = [
        SimpleNamespace(type="reasoning"),
        SimpleNamespace(
            type="function_call", call_id="c1", name="list_insights", arguments='{"limit": 2}'
        ),
    ]
    rec = Recorder(
        SimpleNamespace(
            status="completed",
            output=items,
            output_text="",
            model="configured-model",
            usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        )
    )
    p._client.responses.create = rec  # type: ignore[method-assign]
    transcript = p.start([], "hi")
    turn = await p.converse(
        system="s", transcript=transcript, tools=TOOLS_SPEC, max_output_tokens=9
    )
    assert turn.tool_calls[0].input == {"limit": 2}
    assert rec.kwargs["tools"][0]["type"] == "function"
    p.extend(transcript, turn, [ToolResult("c1", "[]")])
    assert transcript[-1] == {"type": "function_call_output", "call_id": "c1", "output": "[]"}
    assert transcript[1:3] == items
