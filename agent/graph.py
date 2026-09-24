import asyncio
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from mcp_client.sse_aggregator import SseAggregator
from config import GROQ_API_KEY, LLM_MODEL, FALLBACK_LLM_MODEL, BRAND_NAME

EIDIKO_SYSTEM_PROMPT = f"""You are the {BRAND_NAME} Official GitHub MCP AI Assistant.
You are connected to the Official GitHub MCP Server through an MCP stdio container.
You can use the GitHub tools exposed by the server to inspect and modify repositories, code, branches, commits, issues, and pull requests.

Use tools whenever the user asks for live GitHub information or asks you to perform a GitHub operation.
Do not claim an action succeeded until the relevant tool has returned successfully.
When creating or modifying repositories, files, issues, branches, or pull requests, clearly state what was changed.
"""

GROQ_MODEL_CANDIDATES = [LLM_MODEL, FALLBACK_LLM_MODEL]

def _is_model_error(err: str) -> bool:
    text = err.lower()
    return any(k in text for k in [
        "not_found", "404", "model:", "no such model", "does not exist",
        "401", "authentication", "invalid api key", "api_key", "unauthorized"
    ])

def _make_compact_tools_for_groq(tools: List[Any]) -> List[Any]:
    if not tools:
        return []
    # Keep the most commonly used GitHub tools in the model context. The full
    # tool map remains available for execution when the model requests a tool.
    preferred = {
        "list_user_repositories", "search_repositories", "create_repository",
        "create_issue", "list_issues", "get_issue", "create_pull_request",
        "list_pull_requests", "get_file_contents", "create_or_update_file",
        "list_commits", "get_commit", "list_branches", "search_code",
        "search_issues", "fork_repository", "create_branch", "push_files",
        "delete_file", "merge_pull_request"
    }
    selected = [t for t in tools if t.name in preferred]
    if len(selected) < 5:
        selected = tools[:15]

    compact = []
    for t in selected:
        try:
            from langchain_core.tools import StructuredTool
            compact.append(StructuredTool.from_function(
                func=t.func,
                coroutine=t.coroutine,
                name=t.name,
                description=(getattr(t, "description", "") or "")[:300],
                args_schema=t.args_schema,
            ))
        except Exception:
            compact.append(t)
    return compact

def _build_groq_llm(model_name: str, tools: List[Any]):
    from langchain_groq import ChatGroq
    compact_tools = _make_compact_tools_for_groq(tools)
    llm = ChatGroq(
        model=model_name,
        groq_api_key=GROQ_API_KEY,
        temperature=0.1,
        max_tokens=4096,
    )
    return llm.bind_tools(compact_tools) if compact_tools else llm

def get_llm_model(tools: List[Any], requested_model: str = None):
    if not GROQ_API_KEY:
        print("[LLM] GROQ_API_KEY is missing.")
        return None
    model = requested_model or LLM_MODEL
    try:
        llm = _build_groq_llm(model, tools)
        print(f"[LLM] Initialized with Groq model: {model}")
        return llm
    except Exception as exc:
        print(f"[LLM] Could not initialize Groq model {model}: {exc}")
        return None

class EidikoAgentWorkflow:
    def __init__(self, aggregator: SseAggregator = None, model_name: str = None):
        self.aggregator = aggregator or SseAggregator()
        self.model_name = model_name or LLM_MODEL
        tools_res = self.aggregator.discover_tools_sync()
        self.tools = [] if asyncio.iscoroutine(tools_res) or isinstance(tools_res, asyncio.Task) else tools_res
        self.tool_map = {t.name: t for t in self.tools} if self.tools else {}
        self.llm = get_llm_model(self.tools, requested_model=self.model_name)
        self._current_model_idx = 0
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("agent", self._call_agent)
        builder.add_node("action", self._execute_tools)
        builder.set_entry_point("agent")
        builder.add_conditional_edges("agent", self._should_continue, {"continue": "action", "end": END})
        builder.add_edge("action", "agent")
        return builder.compile()

    async def _call_agent(self, state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=EIDIKO_SYSTEM_PROMPT))

        if not self.llm:
            return {"messages": [AIMessage(content="⚠️ Groq is not configured. Add GROQ_API_KEY to .env and restart the application.")]}

        candidates = list(dict.fromkeys([self.model_name, LLM_MODEL, FALLBACK_LLM_MODEL]))
        for idx in range(len(candidates)):
            try:
                response = await self.llm.ainvoke(messages)
                return {"messages": [response]}
            except Exception as exc:
                err = str(exc)
                if not _is_model_error(err) or idx == len(candidates) - 1:
                    raise
                next_model = candidates[idx + 1]
                print(f"[LLM] Model error. Switching Groq model to: {next_model}")
                try:
                    self.model_name = next_model
                    self.llm = _build_groq_llm(next_model, self.tools)
                except Exception:
                    continue

        return {"messages": [AIMessage(content="⚠️ Unable to initialize the configured Groq model. Check the model name and API key.")]}

    def _should_continue(self, state: AgentState) -> str:
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        return "continue" if last_message and getattr(last_message, "tool_calls", None) else "end"

    async def _execute_tools(self, state: AgentState) -> Dict[str, Any]:
        messages = state.get("messages", [])
        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        new_messages, new_steps = [], []

        for tc in tool_calls:
            tname = tc["name"]
            targs = tc.get("args", {})
            call_id = tc.get("id", "call_id")
            lc_tool = self.tool_map.get(tname)
            if lc_tool:
                try:
                    result = await lc_tool.ainvoke(targs) if hasattr(lc_tool, "ainvoke") else lc_tool.invoke(targs)
                    result_str = str(result)
                except Exception as exc:
                    result_str = f"Error executing tool '{tname}': {exc}"
            else:
                result_str = f"Error: Tool '{tname}' is not registered."
            new_messages.append(ToolMessage(content=result_str, tool_call_id=call_id, name=tname))
            new_steps.append({"tool": tname, "server": "Official GitHub MCP Server", "arguments": targs, "result": result_str})

        return {"messages": new_messages, "tool_steps": new_steps}

    async def run(self, user_input: str, history: List[Any] = None) -> Dict[str, Any]:
        messages = list(history or [])
        messages.append(HumanMessage(content=user_input))
        return await self.graph.ainvoke({"messages": messages, "tool_steps": []})
