from __future__ import annotations

from collections.abc import Mapping


MAX_PERSON_TURNS = 6
MAX_OTHER_TURNS = 2
MAX_CONTEXT_CHARS = 10000


def conversation_context(state: Mapping) -> list[dict]:
    """Somente falas já exibidas deste grupo; sem fatos ou instruções internos."""
    valid = []
    owner = state["stakeholder_id"]
    for index, turn in enumerate(state.get("conversation_history", [])):
        if not isinstance(turn, Mapping) or turn.get("error"):
            continue
        analysis = turn.get("analysis")
        analysis = analysis if isinstance(analysis, Mapping) else {}
        if analysis.get("is_prompt_injection") or analysis.get("relevance") == "irrelevant":
            continue
        question, response = turn.get("question"), turn.get("response")
        if not isinstance(question, str) or not isinstance(response, str):
            continue
        if not question.strip() or not response.strip():
            continue
        valid.append({
            "turn_index": index,
            "stakeholder_id": turn.get("stakeholder_id"),
            "same_stakeholder": turn.get("stakeholder_id") == owner,
            "question": question.strip()[:1200],
            "response": response.strip()[:2000],
            "topic": analysis.get("topic"),
        })

    own = [turn for turn in valid if turn["same_stakeholder"]][-MAX_PERSON_TURNS:]
    other = [turn for turn in valid if not turn["same_stakeholder"]][-MAX_OTHER_TURNS:]
    candidates = sorted([*own, *other], key=lambda turn: turn["turn_index"], reverse=True)
    selected, used = [], 0
    for turn in candidates:
        size = len(turn["question"]) + len(turn["response"])
        if used + size > MAX_CONTEXT_CHARS:
            continue
        selected.append(turn)
        used += size
    return list(reversed(selected))


def interpreted_question(state: Mapping) -> str:
    analysis = state.get("question_analysis") or {}
    contextualized = analysis.get("contextualized_question")
    if isinstance(contextualized, str) and contextualized.strip():
        return contextualized.strip()
    return state["current_question"].strip()


def record_timing(analysis: Mapping, stage: str, milliseconds: int) -> dict:
    updated = dict(analysis)
    timings = analysis.get("timings_ms")
    updated["timings_ms"] = dict(timings) if isinstance(timings, Mapping) else {}
    updated["timings_ms"][stage] = max(0, int(milliseconds))
    return updated
