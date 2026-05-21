"""LiteLLM model client."""

from __future__ import annotations

from typing import Any, Protocol

import litellm

from tdec.config import ModelConfig


class ChatModel(Protocol):
    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> str:
        """Return a model response for a chat message list."""


class LiteLLMClient:
    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> str:
        response = litellm.completion(
            model=model.litellm_model_id,
            messages=messages,
            api_base=model.api_base,
            api_key=model.api_key,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
        )
        content: Any = response.choices[0].message.content
        return "" if content is None else str(content)

