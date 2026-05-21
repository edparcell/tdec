"""Debate orchestration."""

from __future__ import annotations

from tdec.config import ModelConfig, TopicConfig
from tdec.debate_types import DebateTranscript, DebateTurn, Side
from tdec.models import ChatModel
from tdec.prompts import DEBATER_SYSTEM_PROMPT, opening_prompt, response_prompt


def run_debate(
    *,
    client: ChatModel,
    topic: TopicConfig,
    pro_model: ModelConfig,
    con_model: ModelConfig,
    rounds: int,
) -> DebateTranscript:
    debate_id = f"{topic.id}__{pro_model.id}_pro__{con_model.id}_con"
    turns: list[DebateTurn] = []
    histories: dict[Side, list[dict[str, str]]] = {
        "pro": [{"role": "system", "content": DEBATER_SYSTEM_PROMPT}],
        "con": [{"role": "system", "content": DEBATER_SYSTEM_PROMPT}],
    }

    for round_number in range(1, rounds + 1):
        for side, model, label in [
            ("pro", pro_model, "A"),
            ("con", con_model, "B"),
        ]:
            prompt = (
                opening_prompt(topic, side, rounds)
                if round_number == 1 and side == "pro"
                else response_prompt(topic, side, round_number, rounds)
            )
            histories[side].append({"role": "user", "content": prompt})
            result = client.call(model, histories[side])
            histories[side].append({"role": "assistant", "content": result.content})

            turn = DebateTurn(
                speaker_label=label,
                speaker_model_id=model.id,
                side=side,
                turn_number=round_number,
                content=result.content,
                metrics=result.metrics,
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


def _share_turn(histories: dict[Side, list[dict[str, str]]], turn: DebateTurn) -> None:
    message = (
        f"Opponent turn just delivered by Debater {turn.speaker_label} "
        f"({turn.side}, turn {turn.turn_number}):\n\n{turn.content}"
    )
    for side in histories:
        if side != turn.side:
            histories[side].append({"role": "user", "content": message})


def debate_pairings(models: list[ModelConfig]) -> list[tuple[ModelConfig, ModelConfig]]:
    pairings = []
    for index, first in enumerate(models):
        for second in models[index + 1 :]:
            pairings.append((first, second))
            pairings.append((second, first))
    return pairings
