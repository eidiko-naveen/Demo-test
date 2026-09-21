from app.graph.state import AgentState


async def synthesize(state: AgentState) -> AgentState:
    """Create the synthesis boundary; the LLM provider is connected in agent phases."""
    return {**state, "final_answer": state.get("final_answer", "")}
