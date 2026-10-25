from __future__ import annotations

from app.domain.interview_state import (
    ConversationTurn,
    InterviewState,
)


def record_interaction(
    state: InterviewState,
) -> dict[str, object]:
    analysis = state["question_analysis"]

    if analysis is None:
        raise ValueError("A pergunta ainda não foi analisada.")

    question = state["current_question"].strip()
    response = state["current_response"].strip()

    if not question:
        raise ValueError("A pergunta atual está vazia.")

    if not response:
        raise ValueError("A resposta atual está vazia.")

    allowed_fact = state["allowed_fact"]

    disclosure_level = (
        allowed_fact["disclosure_level"]
        if allowed_fact is not None
        else None
    )

    turn: ConversationTurn = {
        "question": question,
        "response": response,
        "stakeholder_id": state["stakeholder_id"],
        "analysis": analysis,
        "disclosure_level": disclosure_level,
        "mood": state["mood"],
    }

    updated_history = [
        *state["conversation_history"],
        turn,
    ]

    return {
        "conversation_history": updated_history,
        "error": None,
    }