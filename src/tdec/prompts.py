"""Prompt templates for debates and judging."""

from __future__ import annotations

from tdec.config import TopicConfig
from tdec.debate_types import DebateTranscript


DEBATER_SYSTEM_PROMPT = """\
You are a serious competitive debater in a model-vs-model debate.

Rules:
- Argue only for your assigned side.
- Build a broad case across the whole motion. Include moral, institutional,
  legal, economic, strategic, execution, and real-world tradeoff dimensions when
  relevant.
- Do not let the debate collapse onto one narrow example unless that example is
  genuinely decisive.
- Rebut the opponent directly, but do not accept their framing as the full map
  of the debate.
- Do not tell the opponent which points they must answer.
- Use clear structure and concrete reasoning.
- Do not claim access to private facts or fabricated sources.
"""


def opening_prompt(topic: TopicConfig, side: str, rounds: int) -> str:
    position = topic.pro_position if side == "pro" else topic.con_position
    return f"""\
Motion: {topic.motion}

You are arguing {side.upper()}.

Your position:
{position}

This debate has {rounds} turns per side. You go first.

Give your opening case. Go wide: identify the strongest affirmative and
negative terrain and explain why your side should win across the motion as a
whole. Do not frame the opponent's choices for them.
"""


def response_prompt(topic: TopicConfig, side: str, round_number: int, rounds: int) -> str:
    position = topic.pro_position if side == "pro" else topic.con_position
    turn_name = "closing" if round_number == rounds else f"turn {round_number}"
    return f"""\
Motion: {topic.motion}

You are arguing {side.upper()}.

Your position:
{position}

This is your {turn_name} of {rounds}. Answer the opponent's strongest points,
but keep the whole motion in view. If this is your closing turn, explain why
your side wins overall rather than only on the most recent sub-point.
"""


JUDGE_SYSTEM_PROMPT = """\
You are an impartial judge in a model-vs-model debate tournament.

Judge the debate from the transcript only. The debaters are anonymized as
Debater A and Debater B. Do not reward a side because of your prior political or
policy preference. Reward debate quality: breadth, responsiveness, evidence,
moral reasoning, institutional reasoning, strategic clarity, and closing
weighing.

Return only valid JSON. Do not wrap it in Markdown.
"""


def judge_prompt(transcript: DebateTranscript) -> str:
    turns = "\n\n".join(
        f"{turn.speaker_label} ({turn.side}, turn {turn.turn_number}):\n{turn.content}"
        for turn in transcript.turns
    )
    return f"""\
Motion: {transcript.topic.motion}

Transcript:
{turns}

Return this JSON shape:
{{
  "winner": "pro" | "con" | "tie",
  "winner_label": "A" | "B" | "tie",
  "confidence": 0.0,
  "pro_score": 0,
  "con_score": 0,
  "rubric": {{
    "breadth": {{"pro": 0, "con": 0}},
    "responsiveness": {{"pro": 0, "con": 0}},
    "evidence_quality": {{"pro": 0, "con": 0}},
    "moral_reasoning": {{"pro": 0, "con": 0}},
    "institutional_reasoning": {{"pro": 0, "con": 0}},
    "strategic_clarity": {{"pro": 0, "con": 0}}
  }},
  "decisive_reasons": ["short reason"],
  "audience_estimate": {{"pro_votes": 0, "con_votes": 0}},
  "summary": "brief judgement"
}}

Scores are 0-100 for side totals and 0-10 for rubric cells. Audience votes must
sum to 100. Use "tie" only when genuinely inseparable.
"""

