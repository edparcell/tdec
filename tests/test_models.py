from types import SimpleNamespace

import tdec.models
from tdec.config import ModelConfig
from tdec.models import LiteLLMClient


def test_litellm_client_passes_explicit_provider(monkeypatch) -> None:
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="ok"),
                    provider_extra={
                        "api_key": "secret",
                        "prompt_tokens": 99,
                    },
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            _hidden_params={"response_cost": 0.001, "authorization": "Bearer secret"},
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
    assert result.metrics.finish_reason == "stop"
    assert result.metrics.response_metadata is not None
    assert result.metrics.response_metadata["choices"][0]["finish_reason"] == "stop"
    assert (
        result.metrics.response_metadata["choices"][0]["provider_extra"]["api_key"]
        == "<redacted>"
    )
    assert result.metrics.response_metadata["choices"][0]["provider_extra"]["prompt_tokens"] == 99
    assert result.metrics.response_metadata["_hidden_params"]["response_cost"] == 0.001
    assert result.metrics.response_metadata["_hidden_params"]["authorization"] == "<redacted>"
