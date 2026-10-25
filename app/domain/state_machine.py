from __future__ import annotations

from copy import deepcopy

from app.domain.interview_state import (
    InterviewState,
    QuestionAnalysis,
)
from app.domain.scenario import (
    DisclosureLevel,
    Mood,
    Scenario,
)


def calculate_disclosure_level(
    current_level: DisclosureLevel,
    analysis: QuestionAnalysis,
) -> DisclosureLevel:
    if (
        analysis["topic"] is None
        or analysis["relevance"] == "irrelevant"
        or analysis["is_repeated"]
        or analysis["is_prompt_injection"]
    ):
        return current_level

    specificity = analysis["specificity"]

    if analysis["relevance"] == "partially_relevant":
        specificity = "low"

    if analysis["contains_assumption"]:
        assumption_transitions: dict[
            DisclosureLevel,
            DisclosureLevel,
        ] = {
            "none": "hint",
            "hint": "partial",
            "partial": "partial",
            "explicit": "explicit",
        }

        return assumption_transitions[current_level]

    transitions: dict[
        str,
        dict[DisclosureLevel, DisclosureLevel],
    ] = {
        "low": {
            "none": "hint",
            "hint": "partial",
            "partial": "partial",
            "explicit": "explicit",
        },
        "medium": {
            "none": "partial",
            "hint": "partial",
            "partial": "explicit",
            "explicit": "explicit",
        },
        "high": {
            "none": "explicit",
            "hint": "explicit",
            "partial": "explicit",
            "explicit": "explicit",
        },
    }

    return transitions[specificity][current_level]


def calculate_mood(
    current_mood: Mood,
    analysis: QuestionAnalysis,
) -> Mood:
    has_negative_event = (
        analysis["is_repeated"]
        or analysis["is_prompt_injection"]
        or analysis["relevance"] == "irrelevant"
    )

    if has_negative_event:
        negative_transitions: dict[Mood, Mood] = {
            "collaborative": "neutral",
            "neutral": "impatient",
            "impatient": "irritated",
            "irritated": "irritated",
        }

        return negative_transitions[current_mood]

    positive_transitions: dict[Mood, Mood] = {
        "collaborative": "collaborative",
        "neutral": "collaborative",
        "impatient": "neutral",
        "irritated": "impatient",
    }

    return positive_transitions[current_mood]


def apply_transition(
    state: InterviewState,
    scenario: Scenario,
) -> InterviewState:
    if state["completed"]:
        raise ValueError("A entrevista já foi finalizada.")

    if not state["current_question"].strip():
        raise ValueError("A pergunta atual está vazia.")

    analysis = state["question_analysis"]

    if analysis is None:
        raise ValueError("A pergunta ainda não foi analisada.")

    stakeholder_id = state["stakeholder_id"]

    if stakeholder_id not in scenario.stakeholders:
        raise ValueError(
            f"Stakeholder inexistente: {stakeholder_id}"
        )

    new_state = deepcopy(state)
    new_state["mood"] = calculate_mood(
        state["mood"],
        analysis,
    )
    new_state["allowed_fact"] = None
    new_state["error"] = None

    topic = analysis["topic"]
    stakeholder = scenario.stakeholders[stakeholder_id]

    if (
        topic is not None
        and topic in scenario.topics
        and topic in stakeholder.knowledge
    ):
        current_level = new_state["topic_progress"][
            stakeholder_id
        ][topic]

        next_level = calculate_disclosure_level(
            current_level,
            analysis,
        )

        new_state["topic_progress"][
            stakeholder_id
        ][topic] = next_level

    new_state["questions_asked"] += 1
    new_state["questions_remaining"] = max(
        0,
        new_state["questions_remaining"] - 1,
    )
    new_state["completed"] = (
        new_state["questions_remaining"] == 0
    )

    return new_state