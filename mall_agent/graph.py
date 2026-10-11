from langgraph.graph import StateGraph, START, END

from .state import AgentState
from .nodes import (
    analyze_image,
    understand_intent,
    direct_reply,
    photo_edit,
    search_malls,
    search_hotels_node,
    search_sights,
    search_route,
    search_multi,
    generate_recommend,
    route_after_image,
    route_after_intent,
)


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("analyze_image", analyze_image)
    workflow.add_node("understand_intent", understand_intent)
    workflow.add_node("direct_reply", direct_reply)
    workflow.add_node("photo_edit", photo_edit)
    workflow.add_node("search_malls", search_malls)
    workflow.add_node("search_hotels", search_hotels_node)
    workflow.add_node("search_sights", search_sights)
    workflow.add_node("search_route", search_route)
    workflow.add_node("search_multi", search_multi)
    workflow.add_node("generate_recommend", generate_recommend)

    workflow.add_conditional_edges(
        START,
        route_after_image,
        {
            "analyze_image": "analyze_image",
            "understand_intent": "understand_intent",
        },
    )
    workflow.add_edge("analyze_image", "understand_intent")

    workflow.add_conditional_edges(
        "understand_intent",
        route_after_intent,
        {
            "search_malls": "search_malls",
            "search_hotels": "search_hotels",
            "search_sights": "search_sights",
            "search_route": "search_route",
            "search_multi": "search_multi",
            "direct_reply": "direct_reply",
            "photo_edit": "photo_edit",
            "generate_recommend": "generate_recommend",
        },
    )

    for node in ("search_malls", "search_hotels", "search_sights", "search_route", "search_multi"):
        workflow.add_edge(node, "generate_recommend")

    workflow.add_edge("direct_reply", END)
    workflow.add_edge("photo_edit", END)
    workflow.add_edge("generate_recommend", END)

    return workflow.compile()
