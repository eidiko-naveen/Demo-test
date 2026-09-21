from app.graph.state import AgentState


async def execute_research(state: AgentState) -> AgentState:
    """Execution seam for external research tools."""
    return {**state, "research_results": state.get("research_results", [])}


async def execute_hybrid(state: AgentState) -> AgentState:
    """Execution seam for coordinated enterprise retrieval and external research."""
    return {
        **state,
        "retrieved_documents": state.get("retrieved_documents", []),
        "research_results": state.get("research_results", []),
    }
