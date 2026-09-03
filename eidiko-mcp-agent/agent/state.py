import operator
from typing import Annotated, Sequence, List, Dict, Any, TypedDict
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    State schema for the Eidiko Autonomous DevSecOps LangGraph Agent.
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    tool_steps: Annotated[List[Dict[str, Any]], operator.add]
