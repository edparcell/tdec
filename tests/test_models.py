from types import SimpleNamespace

import tdec.models
from tdec.config import ModelConfig
from tdec.models import LiteLLMClient


def test_litellm_client_passes_explicit_provider(monkeypatch) -> None:
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            _hidden_params={"response_cost": 0.001},
        )

    monkeypatch.setattr(tdec.models.litellm, "completion", fake_completion)

    result = LiteLLMClient().call(
        ModelConfig(
            id="gpt_5_nano",
            provider="openrouter",
            model="openai/gpt-5-nano",
            api_key="test",
            temperature=None,
        ),
        [{"role": "user", "content": "hello"}],
    )

    assert result.content == "ok"
    assert captured["model"] == "openai/gpt-5-nano"
    assert captured["custom_llm_provider"] == "openrouter"
    assert "temperature" not in captured
