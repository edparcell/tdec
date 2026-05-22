"""LangChain chat model that delegates to litellm.completion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from time import perf_counter
from typing import Any

import litellm
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from tdec.config import ModelConfig
from tdec.debate_types import ModelCallMetrics, TokenUsage

ChatModelFactory = Callable[[ModelConfig], BaseChatModel]


class ModelCallError(RuntimeError):
    def __init__(self, model: ModelConfig, cause: Exception) -> None:
        self.model_id = model.id
        self.provider = model.provider
        self.model = model.model
        self.cause = cause
        super().__init__(f"{model.id} ({model.provider}/{model.model}) call failed: {cause}")


class LiteLLMChat(BaseChatModel):
    """A `BaseChatModel` that invokes litellm.completion under the hood.

    We use a custom subclass (rather than `langchain-litellm`'s `ChatLiteLLM`)
    so we can carry the full raw provider response through `response_metadata`
    and surface per-call latency/cost via `additional_kwargs`.
    """

    model_config = ConfigDict(protected_namespaces=())

    tdec_model_id: str
    provider: str
    target_model: str
    api_base: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    max_output_tokens: int = 4096

    @property
    def _llm_type(self) -> str:
        return "litellm-tdec"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        started = perf_counter()
        completion_kwargs: dict[str, Any] = {
            "model": self.target_model,
            "custom_llm_provider": self.provider,
            "messages": _to_litellm_messages(messages),
            "api_base": self.api_base,
            "api_key": self.api_key,
            "max_tokens": self.max_output_tokens,
        }
        if self.temperature is not None:
            completion_kwargs["temperature"] = self.temperature
        if stop is not None:
            completion_kwargs["stop"] = stop
        try:
            response = litellm.completion(**completion_kwargs)
        except Exception as e:
            raise ModelCallError(self._as_model_config(), e) from e

        latency_seconds = perf_counter() - started
        content = response.choices[0].message.content
        cost_usd, cost_error = _extract_cost_info(response, self.provider, self.target_model)
        ai = AIMessage(
            content="" if content is None else str(content),
            additional_kwargs={
                "tdec_latency_seconds": latency_seconds,
                "tdec_cost_usd": cost_usd,
                "tdec_cost_error": cost_error,
            },
            response_metadata=_response_metadata(response),
            usage_metadata=_to_langchain_usage(response),
        )
        return ChatResult(generations=[ChatGeneration(message=ai)])

    def _as_model_config(self) -> ModelConfig:
        return ModelConfig(
            id=self.tdec_model_id,
            provider=self.provider,
            model=self.target_model,
            api_base=self.api_base,
            api_key=self.api_key,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )


def build_chat_model(config: ModelConfig) -> BaseChatModel:
    return LiteLLMChat(
        tdec_model_id=config.id,
        provider=config.provider,
        target_model=config.model,
        api_base=config.api_base,
        api_key=config.api_key,
        temperature=config.temperature,
        max_output_tokens=config.max_tokens,
    )


def invoke_with_metrics(
    chat: BaseChatModel,
    messages: list[BaseMessage],
    model: ModelConfig,
) -> tuple[AIMessage, ModelCallMetrics]:
    """Invoke a chat model and translate the AIMessage extras to ModelCallMetrics.

    Wraps litellm-derived errors so callers see the same `ModelCallError` boundary
    as before. Non-LiteLLMChat models (e.g. test fakes) skip the wrap; they raise
    their own exceptions which already propagate cleanly.
    """
    try:
        ai = chat.invoke(messages)
    except ModelCallError:
        raise
    except Exception as e:
        raise ModelCallError(model, e) from e
    if not isinstance(ai, AIMessage):
        raise TypeError(f"Expected AIMessage from chat.invoke, got {type(ai).__name__}")
    return ai, metrics_from_ai_message(ai, model)


def metrics_from_ai_message(ai: AIMessage, model: ModelConfig) -> ModelCallMetrics:
    extras = ai.additional_kwargs or {}
    response_metadata = ai.response_metadata or {}
    usage = _usage_from_ai_message(ai)
    return ModelCallMetrics(
        model_id=model.id,
        provider=model.provider,
        model=model.model,
        latency_seconds=float(extras.get("tdec_latency_seconds", 0.0)),
        usage=usage,
        cost_usd=extras.get("tdec_cost_usd"),
        cost_error=extras.get("tdec_cost_error"),
        finish_reason=_finish_reason_from_metadata(response_metadata),
        response_metadata=response_metadata or None,
    )


def _to_litellm_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for message in messages:
        role = _role_for(message)
        content = message.content if isinstance(message.content, str) else str(message.content)
        out.append({"role": role, "content": content})
    return out


def _role_for(message: BaseMessage) -> str:
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    return message.type if isinstance(message.type, str) else "user"


def _usage_from_ai_message(ai: AIMessage) -> TokenUsage:
    usage_metadata = getattr(ai, "usage_metadata", None)
    if usage_metadata:
        return TokenUsage(
            prompt_tokens=_int_or_none(usage_metadata.get("input_tokens")),
            completion_tokens=_int_or_none(usage_metadata.get("output_tokens")),
            total_tokens=_int_or_none(usage_metadata.get("total_tokens")),
        )
    return TokenUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None)


def _int_or_none(value: Any) -> int | None:
    return None if value is None else int(value)


def _finish_reason_from_metadata(metadata: dict[str, Any]) -> str | None:
    try:
        value = metadata["choices"][0]["finish_reason"]
    except (KeyError, IndexError, TypeError):
        return None
    return None if value is None else str(value)


def _extract_cost_info(
    response: Any,
    provider: str,
    model: str,
) -> tuple[float | None, str | None]:
    hidden_cost = _hidden_response_cost(response)
    if hidden_cost is not None:
        return hidden_cost, None
    try:
        return (
            float(
                litellm.completion_cost(
                    completion_response=response,
                    model=model,
                    custom_llm_provider=provider,
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


def _to_langchain_usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = _get_usage_value(usage, "prompt_tokens")
    completion = _get_usage_value(usage, "completion_tokens")
    total = _get_usage_value(usage, "total_tokens")
    if prompt is None and completion is None and total is None:
        return None
    return {
        "input_tokens": prompt or 0,
        "output_tokens": completion or 0,
        "total_tokens": total or ((prompt or 0) + (completion or 0)),
    }


def _get_usage_value(usage: Any, name: str) -> int | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        value = usage.get(name)
    else:
        value = getattr(usage, name, None)
    return int(value) if value is not None else None


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
