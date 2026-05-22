"""Shared LangChain chat-model fakes for the test suite."""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from tdec.config import ModelConfig

FakeResponder = Callable[[str, list[BaseMessage]], AIMessage]


class FakeChat(BaseChatModel):
    """A BaseChatModel that delegates to a user-supplied responder.

    `model_id` identifies the underlying tdec ModelConfig. `responder` is a
    callable `(model_id, messages) -> AIMessage` used by tests to script
    behaviour. Both are exposed as Pydantic fields so LangChain's Runnable
    machinery treats this like any other chat model.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, protected_namespaces=())
    model_id: str
    responder: Any

    @property
    def _llm_type(self) -> str:
        return "fake-tdec"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        ai = self.responder(self.model_id, list(messages))
        return ChatResult(generations=[ChatGeneration(message=ai)])


def fake_factory(responder: FakeResponder) -> Callable[[ModelConfig], BaseChatModel]:
    def factory(config: ModelConfig) -> BaseChatModel:
        return FakeChat(model_id=config.id, responder=responder)

    return factory


def fake_ai(
    content: str,
    *,
    cost_usd: float | None = 0.01,
    cost_error: str | None = None,
    latency: float = 1.0,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    response_metadata: dict[str, Any] | None = None,
) -> AIMessage:
    return AIMessage(
        content=content,
        additional_kwargs={
            "tdec_latency_seconds": latency,
            "tdec_cost_usd": cost_usd,
            "tdec_cost_error": cost_error,
        },
        usage_metadata={
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        response_metadata=response_metadata or {},
    )
