import streamlit as st
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.backend.state.state import State
from src.backend.nodes.nodes import (
    file_uploader_node,
    file_relevance_checker_agent,
    fea_planner_agent,
    sme_agent,
    senior_sme_agent,
    consultant_agent,
    coding_agent,
    execution_agent,
    interface_agent,
    global_router
)





@st.cache_resource()
def build_graph():
    checkpointer = MemorySaver()

    graph = StateGraph(State)

    graph.add_node("file_uploader", file_uploader_node)
    graph.add_node("file_relevance_checker", file_relevance_checker_agent)
    graph.add_node("fea_planner", fea_planner_agent)
    graph.add_node("sme", sme_agent)
    graph.add_node("senior_sme", senior_sme_agent)
    graph.add_node("consultant", consultant_agent)
    graph.add_node("coding_agent", coding_agent)
    graph.add_node("execution_agent", execution_agent)
    graph.add_node("interface_agent", interface_agent)


    graph.add_edge(START, "fea_planner")

    graph.add_conditional_edges(
        source="fea_planner",
        path=global_router,
        path_map={
            "route_to_user": END,
            "route_to_file_uploader": "file_uploader",
            "route_to_file_relevance_checker": "file_relevance_checker",
            "route_to_consultant": "consultant",
            "route_to_subject_matter_expert": "sme",
            "route_to_coding_agent": "coding_agent",
            "route_to_interface_agent": "interface_agent"
        },
    )

    graph.add_conditional_edges(
        source="sme",
        path=global_router,
        path_map={
            "route_to_fea_planner": "fea_planner",
            "route_to_senior_sme": "senior_sme",
        },
    )

    graph.add_conditional_edges(
        source="senior_sme",
        path=global_router,
        path_map={
            "route_to_fea_planner": "fea_planner",
            "route_to_sme": "sme",
        },
    )

    graph.add_conditional_edges(
        source="coding_agent",
        path=global_router,
        path_map={
            "route_to_fea_planner": "fea_planner",
            "route_to_execution_agent": "execution_agent",
        },
    )

    graph.add_conditional_edges(
        source="execution_agent",
        path=global_router,
        path_map={
            "route_to_fea_planner": "fea_planner",
            "route_to_coding_agent": "coding_agent",
        },
    )

    graph.add_edge("file_uploader", "file_relevance_checker")
    graph.add_edge("file_relevance_checker", "fea_planner")
    graph.add_edge("consultant", "fea_planner")
    graph.add_edge("interface_agent", "fea_planner")


    return graph.compile(checkpointer=checkpointer)


