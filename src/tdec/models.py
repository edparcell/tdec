"""LiteLLM model client."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
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
            "model": model.model,
            "custom_llm_provider": model.provider,
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
                finish_reason=_extract_finish_reason(response),
                response_metadata=_response_metadata(response),
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
            float(
                litellm.completion_cost(
                    completion_response=response,
                    model=model.model,
                    custom_llm_provider=model.provider,
                )
            ),
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


def _extract_finish_reason(response: Any) -> str | None:
    try:
        value = response.choices[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        return None
    return None if value is None else str(value)


def _response_metadata(response: Any) -> dict[str, Any]:
    data = _to_plain_data(response)
    if not isinstance(data, dict):
        return {"raw_type": type(response).__name__, "raw_repr": repr(response)}
    return _redact_keys(data)


def _to_plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        try:
            return _to_plain_data(value.model_dump(mode="json"))
        except TypeError:
            return _to_plain_data(value.model_dump())
    if is_dataclass(value):
        return _to_plain_data(asdict(value))
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_to_plain_data(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: _to_plain_data(item)
            for key, item in vars(value).items()
            if not key.startswith("__")
        }
    return value


def _redact_keys(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _is_secret_key(key):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_keys(item)
        return redacted
    if isinstance(value, list):
        return [_redact_keys(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    compact = normalized.replace("_", "")
    return compact in {
        "apikey",
        "authorization",
        "key",
        "token",
        "accesstoken",
        "refreshtoken",
        "bearertoken",
        "clientsecret",
        "secret",
    }
