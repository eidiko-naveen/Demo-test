from typing import Any

from app.graph.nodes.memory import load_memory, save_memory
from app.graph.nodes.research import execute_hybrid, execute_research
from app.graph.nodes.retrieval import execute_rag
from app.graph.nodes.routing import set_route, understand_query
from app.graph.nodes.synthesis import synthesize
from app.graph.edges import execution_route
from app.graph.state import AgentState


def build_graph(checkpointer: Any | None = None) -> Any:
    """Build and compile the shared LangGraph workflow with optional checkpoint memory."""
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install the 'rag' extras to use LangGraph orchestration") from exc

    graph = StateGraph(AgentState)
    graph.add_node("load_memory", load_memory)
    graph.add_node("understand_query", understand_query)
    graph.add_node("route_agent", set_route)
    graph.add_node("rag", execute_rag)
    graph.add_node("research", execute_research)
    graph.add_node("hybrid", execute_hybrid)
    graph.add_node("synthesize", synthesize)
    graph.add_node("save_memory", save_memory)
    graph.add_edge(START, "load_memory")
    graph.add_edge("load_memory", "understand_query")
    graph.add_edge("understand_query", "route_agent")
    graph.add_conditional_edges(
        "route_agent",
        execution_route,
        {"rag": "rag", "research": "research", "hybrid": "hybrid"},
    )
    graph.add_edge("rag", "synthesize")
    graph.add_edge("research", "synthesize")
    graph.add_edge("hybrid", "synthesize")
    graph.add_edge("synthesize", "save_memory")
    graph.add_edge("save_memory", END)
    resolved_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=resolved_checkpointer)
