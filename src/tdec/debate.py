"""Debate orchestration on top of LangChain chains."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tdec.config import ModelConfig, TopicConfig
from tdec.debate_types import DebateTranscript, DebateTurn, Side
from tdec.models import (
    ChatModelFactory,
    ModelCallError,
    metrics_from_ai_message,
)
from tdec.prompts import DEBATER_SYSTEM_PROMPT, opening_prompt, response_prompt

DEBATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", DEBATER_SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{turn_prompt}"),
    ]
)


def run_debate(
    *,
    chat_factory: ChatModelFactory,
    topic: TopicConfig,
    pro_model: ModelConfig,
    con_model: ModelConfig,
    rounds: int,
) -> DebateTranscript:
    debate_id = f"{topic.id}__{pro_model.id}_pro__{con_model.id}_con"
    models = {"pro": pro_model, "con": con_model}
    chats = {side: chat_factory(model) for side, model in models.items()}
    chains = {side: DEBATE_PROMPT | chat for side, chat in chats.items()}
    histories: dict[Side, list[BaseMessage]] = {"pro": [], "con": []}
    turns: list[DebateTurn] = []

    for round_number in range(1, rounds + 1):
        for side, label in [("pro", "A"), ("con", "B")]:
            turn_prompt = (
                opening_prompt(topic, side, rounds)
                if round_number == 1 and side == "pro"
                else response_prompt(topic, side, round_number, rounds)
            )
            try:
                ai = chains[side].invoke(
                    {"history": list(histories[side]), "turn_prompt": turn_prompt}
                )
            except ModelCallError:
                raise
            except Exception as e:
                raise ModelCallError(models[side], e) from e
            if not isinstance(ai, AIMessage):
                raise TypeError(f"Expected AIMessage from chain, got {type(ai).__name__}")

            metrics = metrics_from_ai_message(ai, models[side])
            histories[side].append(HumanMessage(content=turn_prompt))
            histories[side].append(ai)

            turn = DebateTurn(
                speaker_label=label,
                speaker_model_id=models[side].id,
                side=side,
                turn_number=round_number,
                content=str(ai.content),
                metrics=metrics,
            )
            turns.append(turn)
            _share_turn(histories, turn)

    return DebateTranscript(
        id=debate_id,
        topic=topic,
        pro_model=pro_model,
        con_model=con_model,
        rounds=rounds,
        turns=turns,
    )


def _share_turn(histories: dict[Side, list[BaseMessage]], turn: DebateTurn) -> None:
    message = (
        f"Opponent turn just delivered by Debater {turn.speaker_label} "
        f"({turn.side}, turn {turn.turn_number}):\n\n{turn.content}"
    )
    for side in histories:
        if side != turn.side:
            histories[side].append(HumanMessage(content=message))


def debate_pairings(
    models: list[ModelConfig],
    *,
    include_self_debates: bool = True,
) -> list[tuple[ModelConfig, ModelConfig]]:
    pairings = []
    for index, first in enumerate(models):
        if include_self_debates:
            pairings.append((first, first))
        for second in models[index + 1 :]:
            pairings.append((first, second))
            pairings.append((second, first))
    return pairings
