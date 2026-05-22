"""LiteLLM model client."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol

import litellm

from tdec.config import ModelConfig
from tdec.debate_types import ModelCallMetrics, ModelCallResult, TokenUsage


class ChatModel(Protocol):
    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> ModelCallResult:
        """Return a model response for a chat message list."""


class LiteLLMClient:
    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> ModelCallResult:
        started = perf_counter()
        kwargs = {
            "model": model.litellm_model_id,
            "messages": messages,
            "api_base": model.api_base,
            "api_key": model.api_key,
            "max_tokens": model.max_tokens,
        }
        if model.temperature is not None:
            kwargs["temperature"] = model.temperature
        response = litellm.completion(**kwargs)
        latency_seconds = perf_counter() - started
        content: Any = response.choices[0].message.content
        cost_usd, cost_error = _extract_cost_info(response, model)
        return ModelCallResult(
            content="" if content is None else str(content),
            metrics=ModelCallMetrics(
                model_id=model.id,
                provider=model.provider,
                model=model.model,
                latency_seconds=latency_seconds,
                usage=_extract_usage(response),
                cost_usd=cost_usd,
                cost_error=cost_error,
            ),
        )


def _extract_usage(response: Any) -> TokenUsage:
    usage = getattr(response, "usage", None)
    return TokenUsage(
        prompt_tokens=_get_usage_value(usage, "prompt_tokens"),
        completion_tokens=_get_usage_value(usage, "completion_tokens"),
        total_tokens=_get_usage_value(usage, "total_tokens"),
    )


def _get_usage_value(usage: Any, name: str) -> int | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        value = usage.get(name)
    else:
        value = getattr(usage, name, None)
    return int(value) if value is not None else None


def _extract_cost_info(response: Any, model: ModelConfig) -> tuple[float | None, str | None]:
    hidden_cost = _hidden_response_cost(response)
    if hidden_cost is not None:
        return hidden_cost, None
    try:
        return (
            float(litellm.completion_cost(completion_response=response, model=model.litellm_model_id)),
            None,
        )
    except Exception as e:
        return None, str(e)


def _hidden_response_cost(response: Any) -> float | None:
    hidden = getattr(response, "_hidden_params", None)
    if not isinstance(hidden, dict):
        return None
    value = hidden.get("response_cost")
    return float(value) if value is not None else None
