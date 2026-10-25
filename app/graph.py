from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.domain.interview_state import InterviewState
from app.domain.scenario import Scenario
from app.nodes.analyze_question import (
    create_analyze_question_node,
)
from app.nodes.apply_transition import (
    create_apply_transition_node,
)
from app.nodes.generate_response import (
    create_generate_response_node,
)
from app.nodes.record_interaction import record_interaction
from app.nodes.select_facts import create_select_facts_node


def create_interview_graph(scenario: Scenario):
    graph_builder = StateGraph(InterviewState)

    graph_builder.add_node(
        "analyze_question",
        create_analyze_question_node(scenario),
    )
    graph_builder.add_node(
        "apply_transition",
        create_apply_transition_node(scenario),
    )
    graph_builder.add_node(
        "select_facts",
        create_select_facts_node(scenario),
    )
    graph_builder.add_node(
        "generate_response",
        create_generate_response_node(scenario),
    )
    graph_builder.add_node(
        "record_interaction",
        record_interaction,
    )

    graph_builder.add_edge(
        START,
        "analyze_question",
    )
    graph_builder.add_edge(
        "analyze_question",
        "apply_transition",
    )
    graph_builder.add_edge(
        "apply_transition",
        "select_facts",
    )
    graph_builder.add_edge(
        "select_facts",
        "generate_response",
    )
    graph_builder.add_edge(
        "generate_response",
        "record_interaction",
    )
    graph_builder.add_edge(
        "record_interaction",
        END,
    )

    return graph_builder.compile()