"""Debate orchestration."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from tdec.config import DebaterConfig, TopicConfig
from tdec.debate_types import DebateTranscript, DebateTurn, ModelCallResult, Side
from tdec.models import ChatModel
from tdec.prompts import PromptSet


class OpeningCache:
    """Thread-safe cache for reusing opening statements across debates."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], ModelCallResult] = {}
        self._key_locks: dict[tuple[str, str, str], threading.Lock] = {}
        self._global_lock = threading.Lock()

    def get_or_call(
        self,
        key: tuple[str, str, str],
        fn: callable,
    ) -> ModelCallResult:
        with self._global_lock:
            if key in self._cache:
                return self._cache[key]
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            key_lock = self._key_locks[key]

        with key_lock:
            if key in self._cache:
                return self._cache[key]
            result = fn()
            self._cache[key] = result
            return result


def run_debate(
    *,
    client: ChatModel,
    topic: TopicConfig,
    pro_model: DebaterConfig,
    con_model: DebaterConfig,
    rounds: int,
    prompt_set: PromptSet,
    opening_cache: OpeningCache | None = None,
) -> DebateTranscript:
    debate_id = f"{topic.id}__{pro_model.id}_pro__{con_model.id}_con"
    turns: list[DebateTurn] = []
    histories: dict[Side, list[dict[str, str]]] = {
        "pro": [{"role": "system", "content": prompt_set.render_debater_system(strategy=pro_model.strategy)}],
        "con": [{"role": "system", "content": prompt_set.render_debater_system(strategy=con_model.strategy)}],
    }

    for round_number in range(1, rounds + 1):
        for side, model, label in [
            ("pro", pro_model, "A"),
            ("con", con_model, "B"),
        ]:
            is_pro_opening = round_number == 1 and side == "pro"
            if is_pro_opening:
                prompt = prompt_set.render_opening(
                    motion=topic.motion, context=topic.context,
                    side=side, rounds=rounds,
                )
            else:
                prompt = prompt_set.render_response(
                    motion=topic.motion, context=topic.context,
                    side=side, round_number=round_number, rounds=rounds,
                )
            histories[side].append({"role": "user", "content": prompt})

            if is_pro_opening and opening_cache is not None:
                cache_key = (model.id, topic.id, "pro")
                result = opening_cache.get_or_call(
                    cache_key, lambda: client.call(model, histories[side])
                )
            else:
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


def run_parallel_debate(
    *,
    client: ChatModel,
    topic: TopicConfig,
    pro_model: DebaterConfig,
    con_model: DebaterConfig,
    rounds: int,
    prompt_set: PromptSet,
    opening_cache: OpeningCache | None = None,
) -> DebateTranscript:
    debate_id = f"{topic.id}__{pro_model.id}_pro__{con_model.id}_con"
    turns: list[DebateTurn] = []
    histories: dict[Side, list[dict[str, str]]] = {
        "pro": [{"role": "system", "content": prompt_set.render_debater_system(strategy=pro_model.strategy)}],
        "con": [{"role": "system", "content": prompt_set.render_debater_system(strategy=con_model.strategy)}],
    }

    sides: list[tuple[Side, DebaterConfig, str]] = [
        ("pro", pro_model, "A"),
        ("con", con_model, "B"),
    ]

    for round_number in range(1, rounds + 1):
        for side, _model, _label in sides:
            if round_number == 1:
                prompt = prompt_set.render_parallel_opening(
                    motion=topic.motion, context=topic.context,
                    side=side, rounds=rounds,
                )
            else:
                prompt = prompt_set.render_parallel_response(
                    motion=topic.motion, context=topic.context,
                    side=side, round_number=round_number, rounds=rounds,
                )
            histories[side].append({"role": "user", "content": prompt})

        def _call_side(side: Side, model: DebaterConfig) -> ModelCallResult:
            if round_number == 1 and opening_cache is not None:
                cache_key = (model.id, topic.id, side)
                return opening_cache.get_or_call(
                    cache_key, lambda: client.call(model, histories[side])
                )
            return client.call(model, histories[side])

        with ThreadPoolExecutor(max_workers=2) as executor:
            pro_future = executor.submit(_call_side, "pro", pro_model)
            con_future = executor.submit(_call_side, "con", con_model)
            results: dict[Side, ModelCallResult] = {
                "pro": pro_future.result(),
                "con": con_future.result(),
            }

        round_turns: list[DebateTurn] = []
        for side, model, label in sides:
            result = results[side]
            histories[side].append({"role": "assistant", "content": result.content})
            turn = DebateTurn(
                speaker_label=label,
                speaker_model_id=model.id,
                side=side,
                turn_number=round_number,
                content=result.content,
                metrics=result.metrics,
            )
            round_turns.append(turn)

        _share_round(histories, round_turns)
        turns.extend(round_turns)

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


def _share_round(
    histories: dict[Side, list[dict[str, str]]], round_turns: list[DebateTurn]
) -> None:
    for turn in round_turns:
        message = (
            f"Round {turn.turn_number} delivery by Debater {turn.speaker_label} "
            f"({turn.side}):\n\n{turn.content}"
        )
        for side in histories:
            if side != turn.side:
                histories[side].append({"role": "user", "content": message})


def debate_pairings(
    models: list[DebaterConfig],
    *,
    include_self_debates: bool = True,
) -> list[tuple[DebaterConfig, DebaterConfig]]:
    pairings = []
    for index, first in enumerate(models):
        if include_self_debates:
            pairings.append((first, first))
        for second in models[index + 1 :]:
            pairings.append((first, second))
            pairings.append((second, first))
    return pairings
