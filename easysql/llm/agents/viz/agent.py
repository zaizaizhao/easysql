"""
Visualization planning LangGraph agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from easysql.llm.agents.viz.nodes import plan_viz_node, preprocess_node, validate_plan_node
from easysql.llm.agents.viz.state import VizState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def build_viz_graph() -> "CompiledStateGraph":
    builder = StateGraph(VizState)

    builder.add_node("preprocess", preprocess_node)
    builder.add_node("plan", plan_viz_node)
    builder.add_node("validate", validate_plan_node)

    builder.add_edge(START, "preprocess")
    builder.add_edge("preprocess", "plan")
    builder.add_edge("plan", "validate")
    builder.add_edge("validate", END)

    return builder.compile()
