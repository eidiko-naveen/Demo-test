from app.graph.state import AgentState


async def execute_rag(state: AgentState) -> AgentState:
    """Execution seam for the enterprise retriever and RAG agent."""
    return {**state, "retrieved_documents": state.get("retrieved_documents", [])}
