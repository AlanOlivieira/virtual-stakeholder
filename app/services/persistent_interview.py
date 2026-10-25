from __future__ import annotations

from copy import deepcopy
from time import perf_counter

from app.infrastructure.interview_repository import TurnTicket


MOODS = {"neutral", "collaborative", "impatient", "irritated"}


def prepare_turn(ticket: TurnTicket) -> dict:
    state = deepcopy(ticket.interview.state)
    person = ticket.interview.scenario_snapshot["stakeholders"][ticket.stakeholder_id]
    state.update(
        stakeholder_id=ticket.stakeholder_id,
        current_question=ticket.question,
        current_response="",
        question_analysis=None,
        allowed_fact=None,
        allowed_facts=[],
        error=None,
    )
    state["mood"] = person.get("initial_mood", "neutral")
    for turn in reversed(state["conversation_history"]):
        if turn["stakeholder_id"] == ticket.stakeholder_id:
            if turn.get("mood") in MOODS:
                state["mood"] = turn["mood"]
            break
    return state


def generate_turn(graph, ticket: TurnTicket) -> tuple[dict, int]:
    started = perf_counter()
    updated = graph.invoke(prepare_turn(ticket))
    if updated.get("error"):
        raise RuntimeError("O grafo informou falha no processamento.")
    if not str(updated.get("current_response", "")).strip():
        raise RuntimeError("O grafo retornou uma resposta vazia.")
    return dict(updated), round((perf_counter() - started) * 1000)


def student_report(interview) -> dict:
    """Somente conteúdo que o estudante viu. Sem análise, gabarito ou fatos internos."""
    state = interview.state
    people = interview.scenario_snapshot["stakeholders"]
    return {
        "session_id": interview.id,
        "group_name": interview.group_name,
        "scenario_id": state["scenario_id"],
        "questions_asked": state["questions_asked"],
        "questions_remaining": state["questions_remaining"],
        "completed": state["completed"],
        "conversation_history": [
            {
                "stakeholder_id": turn["stakeholder_id"],
                "stakeholder_name": people.get(turn["stakeholder_id"], {}).get("name", "Personagem"),
                "question": turn["question"],
                "response": turn["response"],
            }
            for turn in state["conversation_history"]
        ],
    }
