from app.graph.state import AgentState, RouteType


def execution_route(state: AgentState) -> RouteType:
    """Return the route selected by the routing node for conditional graph edges."""
    return state.get("route", "rag")
