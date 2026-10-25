from __future__ import annotations

from typing import Literal, TypedDict
from uuid import uuid4

from app.domain.scenario import (
    Authority,
    DisclosureLevel,
    FactType,
    Mood,
    Scenario,
)


Specificity = Literal["low", "medium", "high"]
QuestionType = Literal["open", "closed"]
Relevance = Literal["relevant", "partially_relevant", "irrelevant"]


class _QuestionContext(TypedDict, total=False):
    contextualized_question: str
    is_follow_up: bool
    needs_clarification: bool
    seeks_additional_information: bool
    timings_ms: dict[str, int]


class QuestionAnalysis(_QuestionContext):
    topic: str | None
    specificity: Specificity
    question_type: QuestionType
    contains_assumption: bool
    is_repeated: bool
    is_prompt_injection: bool
    relevance: Relevance


class AllowedFact(TypedDict):
    fact_id: str
    topic: str
    disclosure_level: DisclosureLevel
    content: str
    fact_type: FactType
    authority: Authority


class _ConversationSources(TypedDict, total=False):
    allowed_fact: AllowedFact | None
    allowed_facts: list[AllowedFact]


class ConversationTurn(_ConversationSources):
    question: str
    response: str
    stakeholder_id: str
    analysis: QuestionAnalysis
    disclosure_level: DisclosureLevel | None
    mood: Mood


class InterviewState(TypedDict):
    session_id: str
    scenario_id: str
    stakeholder_id: str

    current_question: str
    current_response: str
    questions_asked: int
    questions_remaining: int

    question_analysis: QuestionAnalysis | None
    allowed_fact: AllowedFact | None
    allowed_facts: list[AllowedFact]

    mood: Mood
    topic_progress: dict[str, dict[str, DisclosureLevel]]
    unlocked_facts: list[str]
    conversation_history: list[ConversationTurn]

    completed: bool
    error: str | None


def create_initial_state(
    scenario: Scenario,
    session_id: str | None = None,
    stakeholder_id: str | None = None,
) -> InterviewState:
    selected_stakeholder_id = (
        stakeholder_id
        or scenario.interview_config.initial_stakeholder_id
    )

    if selected_stakeholder_id not in scenario.stakeholders:
        raise ValueError(
            f"Stakeholder inexistente: {selected_stakeholder_id}"
        )

    selected_stakeholder = scenario.stakeholders[selected_stakeholder_id]

    topic_progress: dict[str, dict[str, DisclosureLevel]] = {
        current_stakeholder_id: {
            topic_id: "none"
            for topic_id in current_stakeholder.knowledge
        }
        for current_stakeholder_id, current_stakeholder
        in scenario.stakeholders.items()
    }

    if selected_stakeholder_id == scenario.interview_config.initial_stakeholder_id:
        greeting = scenario.interview_config.greeting
    else:
        greeting = (
            f"Olá! Sou {selected_stakeholder.name}. "
            "Pode me perguntar sobre minha participação nas monitorias "
            "e o que espero do sistema."
        )

    return InterviewState(
        session_id=session_id or str(uuid4()),
        scenario_id=scenario.id,
        stakeholder_id=selected_stakeholder_id,
        current_question="",
        current_response=greeting,
        questions_asked=0,
        questions_remaining=scenario.interview_config.max_questions,
        question_analysis=None,
        allowed_fact=None,
        allowed_facts=[],
        mood=selected_stakeholder.initial_mood,
        topic_progress=topic_progress,
        unlocked_facts=[],
        conversation_history=[],
        completed=False,
        error=None,
    )
