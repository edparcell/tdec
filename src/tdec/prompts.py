"""Prompt rendering via configurable template sets."""

from __future__ import annotations

from string import Template

from tdec.config import PromptSetConfig
from tdec.debate_types import DebateTranscript


class PromptSet:
    """Renders debate and judge prompts from a PromptSetConfig."""

    def __init__(self, config: PromptSetConfig) -> None:
        self._config = config

    def render_debater_system(self, *, strategy: str | None = None) -> str:
        strategy_block = f"Your approach: {strategy.strip()}\n" if strategy else ""
        return Template(self._config.debater_system).safe_substitute(
            strategy_block=strategy_block,
        )

    def render_opening(
        self, *, motion: str, context: str | None, side: str, rounds: int
    ) -> str:
        return Template(self._config.opening).safe_substitute(
            motion=motion,
            context_block=_context_block(context),
            side=side.upper(),
            rounds=str(rounds),
        )

    def render_response(
        self,
        *,
        motion: str,
        context: str | None,
        side: str,
        round_number: int,
        rounds: int,
    ) -> str:
        turn_name = "closing" if round_number == rounds else f"turn {round_number}"
        return Template(self._config.response).safe_substitute(
            motion=motion,
            context_block=_context_block(context),
            side=side.upper(),
            turn_name=turn_name,
            rounds=str(rounds),
        )

    def render_parallel_opening(
        self, *, motion: str, context: str | None, side: str, rounds: int
    ) -> str:
        return Template(self._config.parallel_opening).safe_substitute(
            motion=motion,
            context_block=_context_block(context),
            side=side.upper(),
            rounds=str(rounds),
        )

    def render_parallel_response(
        self,
        *,
        motion: str,
        context: str | None,
        side: str,
        round_number: int,
        rounds: int,
    ) -> str:
        turn_name = "closing" if round_number == rounds else f"turn {round_number}"
        return Template(self._config.parallel_response).safe_substitute(
            motion=motion,
            context_block=_context_block(context),
            side=side.upper(),
            turn_name=turn_name,
            rounds=str(rounds),
        )

    def render_judge_system(
        self, *, style: str | None = None, parallel: bool = False
    ) -> str:
        style_block = f"{style.strip()}\n" if style else ""
        template_text = (
            self._config.parallel_judge_system if parallel
            else self._config.judge_system
        )
        return Template(template_text).safe_substitute(
            style_block=style_block,
        )

    def render_judge(self, *, transcript: DebateTranscript) -> str:
        # Show only the anonymized A/B label, never the pro/con side. Leaking
        # the side defeats the label-swap (relabel) bias experiment and the
        # judge-system promise that debaters are anonymized as A and B.
        transcript_text = "\n\n".join(
            f"Debater {t.speaker_label} (turn {t.turn_number}):\n{t.content}"
            for t in transcript.turns
        )
        return Template(self._config.judge).safe_substitute(
            motion=transcript.topic.motion,
            transcript=transcript_text,
        )

    def render_judge_repair(self, *, bad_output: str, error: str) -> str:
        return Template(self._config.judge_repair).safe_substitute(
            bad_output=bad_output,
            error=error,
        )


def _context_block(context: str | None) -> str:
    if not context:
        return ""
    return f"\nContext:\n{context.strip()}\n"
