from __future__ import annotations

from collections.abc import Callable

from app.domain.interview_state import InterviewState
from app.domain.scenario import Scenario
from app.domain.state_machine import (
    apply_transition as apply_state_transition,
)


def create_apply_transition_node(
    scenario: Scenario,
) -> Callable[[InterviewState], dict[str, object]]:
    def apply_transition_node(
        state: InterviewState,
    ) -> dict[str, object]:
        updated_state = apply_state_transition(
            state,
            scenario,
        )

        return {
            "mood": updated_state["mood"],
            "topic_progress": updated_state["topic_progress"],
            "questions_asked": updated_state["questions_asked"],
            "questions_remaining": (
                updated_state["questions_remaining"]
            ),
            "allowed_fact": None,
            "completed": updated_state["completed"],
            "error": None,
        }

    return apply_transition_node