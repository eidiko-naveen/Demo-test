from app.graph.state import AgentState, RouteType


def understand_query(state: AgentState) -> AgentState:
    """Capture a small routing hint without allowing it to override explicit selection."""
    query = state.get("query", "").lower()
    research_hint = any(
        phrase in query
        for phrase in ("latest", "current", "today", "recent", "industry practice", "research")
    )
    return {**state, "metadata": {**state.get("metadata", {}), "research_hint": research_hint}}


def route_agent(state: AgentState) -> RouteType:
    """Choose an execution path; explicit agent selection always has priority."""
    selected_agent = state.get("agent_type", "rag")
    if selected_agent in {"rag", "research", "hybrid"}:
        if selected_agent != "hybrid":
            return selected_agent
        if state.get("metadata", {}).get("research_hint"):
            return "hybrid"
        return "hybrid"
    return "rag"


def set_route(state: AgentState) -> AgentState:
    return {**state, "route": route_agent(state)}
