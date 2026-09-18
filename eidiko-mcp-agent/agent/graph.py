import asyncio
import json
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from mcp_client.sse_aggregator import SseAggregator
from config import ANTHROPIC_API_KEY, GROQ_API_KEY, LLM_MODEL, FALLBACK_LLM_MODEL, BRAND_NAME

EIDIKO_SYSTEM_PROMPT = f"""You are the {BRAND_NAME} Official GitHub MCP AI Assistant.
You are connected directly to the Official GitHub MCP Server via HTTP/SSE.
You have access to 42+ official GitHub API tools including:
- Repository Management: search_repositories, create_repository, fork_repository, list_repository_collaborators
- Code & Files: get_file_contents, create_or_update_file, delete_file, push_files, search_code
- Branches & Commits: create_branch, list_branches, get_commit, list_commits, search_commits
- Issues & PRs: list_issues, create_issue/issue_write, list_pull_requests, create_pull_request, merge_pull_request, pull_request_read

Always provide helpful, precise, and executive-focused assistance for GitHub operations.
When creating or modifying repositories/files, explain the exact actions taken.
"""

# Ordered list of Claude models to try (newest/best first)
ANTHROPIC_MODEL_CANDIDATES = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]

GROQ_MODEL_CANDIDATES = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3.6-27b",
]

def _is_model_error(err: str) -> bool:
    """Return True if the error is a model-not-found, 404, or API key authentication error."""
    err_lower = err.lower()
    return any(k in err_lower for k in [
        "not_found", "404", "model:", "no such model", "does not exist",
        "401", "authentication_error", "invalid x-api-key", "invalid_api_key", "unauthorized", "api_key"
    ])

def _build_anthropic_llm(model_name: str, tools: List[Any]):
    from langchain_anthropic import ChatAnthropic
    llm = ChatAnthropic(
        model=model_name,
        anthropic_api_key=ANTHROPIC_API_KEY,
        temperature=0.1,
        max_tokens=4096,
    )
    return llm.bind_tools(tools) if tools else llm

def _make_compact_tools_for_groq(tools: List[Any]) -> List[Any]:
    if not tools:
        return []
    top_tool_names = {
        "list_user_repositories", "search_repositories", "create_repository",
        "create_issue", "list_issues", "get_issue",
        "create_pull_request", "list_pull_requests", "get_file_contents",
        "create_or_update_file", "list_commits", "get_commit",
        "list_branches", "search_code", "search_issues"
    }
    selected_tools = [t for t in tools if t.name in top_tool_names]
    if len(selected_tools) < 5:
        selected_tools = tools[:15]

    compact_tools = []
    for t in selected_tools:
        short_desc = (getattr(t, "description", "") or "")[:80]
        try:
            from langchain_core.tools import StructuredTool
            c_tool = StructuredTool.from_function(
                func=t.func,
                coroutine=t.coroutine,
                name=t.name,
                description=short_desc,
                args_schema=t.args_schema
            )
            compact_tools.append(c_tool)
        except Exception:
            compact_tools.append(t)
    return compact_tools

def _build_groq_llm(model_name: str, tools: List[Any]):
    from langchain_groq import ChatGroq
    compact_tools = _make_compact_tools_for_groq(tools)
    llm = ChatGroq(
        model=model_name,
        groq_api_key=GROQ_API_KEY,
        temperature=0.1,
        max_tokens=2048,
    )
    return llm.bind_tools(compact_tools) if compact_tools else llm

def get_llm_model(tools: List[Any], requested_model: str = None):
    req = (requested_model or "").lower()
    is_groq_req = any(req.startswith(prefix) for prefix in ["llama", "qwen", "groq", "openai/"])

    if is_groq_req and GROQ_API_KEY:
        try:
            start_model = requested_model or FALLBACK_LLM_MODEL
            ordered = list(dict.fromkeys([start_model] + GROQ_MODEL_CANDIDATES))
            bound = _build_groq_llm(ordered[0], tools)
            print(f"[LLM] Initialized with Groq model: {ordered[0]}")
            return bound
        except Exception as e:
            print(f"[LLM] Could not build Groq LLM: {e}")

    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY not in ("", "your_anthropic_api_key_here"):
        start_model = requested_model or LLM_MODEL
        ordered = list(dict.fromkeys([start_model] + ANTHROPIC_MODEL_CANDIDATES))
        try:
            bound = _build_anthropic_llm(ordered[0], tools)
            print(f"[LLM] Initialized with Anthropic model: {ordered[0]}")
            return bound
        except Exception as e:
            print(f"[LLM] Could not build Anthropic LLM: {e}")

    if GROQ_API_KEY:
        try:
            start_model = requested_model or FALLBACK_LLM_MODEL
            ordered = list(dict.fromkeys([start_model] + GROQ_MODEL_CANDIDATES))
            bound = _build_groq_llm(ordered[0], tools)
            print(f"[LLM] Initialized with Groq model: {ordered[0]}")
            return bound
        except Exception as e:
            print(f"[LLM] Could not build Groq LLM: {e}")

    print("[LLM] ❌ No LLM available.")
    return None

class EidikoAgentWorkflow:
    def __init__(self, aggregator: SseAggregator = None, model_name: str = None):
        self.aggregator = aggregator or SseAggregator()
        self.model_name = model_name
        tools_res = self.aggregator.discover_tools_sync()
        if asyncio.iscoroutine(tools_res) or isinstance(tools_res, asyncio.Task):
            self.tools = []
        else:
            self.tools = tools_res
        self.tool_map = {t.name: t for t in self.tools} if self.tools else {}
        self.llm = get_llm_model(self.tools, requested_model=model_name)
        self._current_model_idx = 0
        req_name = (model_name or "").lower()
        self._using_groq = any(req_name.startswith(p) for p in ["llama", "qwen", "groq", "openai/"])
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("agent", self._call_agent)
        builder.add_node("action", self._execute_tools)
        builder.set_entry_point("agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "action",
                "end": END
            }
        )
        builder.add_edge("action", "agent")
        return builder.compile()

    async def _call_agent(self, state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=EIDIKO_SYSTEM_PROMPT))

        if self.llm:
            anthropic_candidates = list(dict.fromkeys([LLM_MODEL] + ANTHROPIC_MODEL_CANDIDATES))
            groq_candidates = list(dict.fromkeys([FALLBACK_LLM_MODEL] + GROQ_MODEL_CANDIDATES))

            for attempt in range(len(anthropic_candidates) + len(groq_candidates) + 1):
                try:
                    response = await self.llm.ainvoke(messages)
                    return {"messages": [response]}
                except Exception as e:
                    err = str(e)
                    if not _is_model_error(err):
                        raise

                    if not self._using_groq:
                        self._current_model_idx += 1
                        if self._current_model_idx < len(anthropic_candidates):
                            next_model = anthropic_candidates[self._current_model_idx]
                            print(f"[LLM] ⚠️ Model not found. Switching to: {next_model}")
                            try:
                                self.llm = _build_anthropic_llm(next_model, self.tools)
                                continue
                            except Exception:
                                pass

                        if GROQ_API_KEY:
                            self._using_groq = True
                            self._current_model_idx = 0
                            next_model = groq_candidates[0]
                            print(f"[LLM] ⚠️ All Claude models exhausted. Switching to Groq: {next_model}")
                            try:
                                self.llm = _build_groq_llm(next_model, self.tools)
                                continue
                            except Exception:
                                pass
                    else:
                        self._current_model_idx += 1
                        if self._current_model_idx < len(groq_candidates):
                            next_model = groq_candidates[self._current_model_idx]
                            print(f"[LLM] ⚠️ Groq model failed. Trying: {next_model}")
                            try:
                                self.llm = _build_groq_llm(next_model, self.tools)
                                continue
                            except Exception:
                                pass

                    print("[LLM] ❌ All LLM models exhausted.")
                    self.llm = None
                    return {"messages": [AIMessage(content=f"⚠️ **Model Authentication Error**: Unable to reach `{self.model_name}`. Please check your API keys in `.env`. Details: {err}")]}

        ai_msg = AIMessage(content="Greeting from Eidiko GitHub Assistant. Please configure your API key to interact with GitHub tools.")
        return {"messages": [ai_msg]}

    def _should_continue(self, state: AgentState) -> str:
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        if last_message and getattr(last_message, "tool_calls", None):
            return "continue"
        return "end"

    async def _execute_tools(self, state: AgentState) -> Dict[str, Any]:
        messages = state.get("messages", [])
        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", [])

        new_messages = []
        new_steps = []

        for tc in tool_calls:
            tname = tc["name"]
            targs = tc["args"]
            call_id = tc.get("id", "call_id")

            lc_tool = self.tool_map.get(tname)
            if lc_tool:
                try:
                    if hasattr(lc_tool, "ainvoke"):
                        result = await lc_tool.ainvoke(targs)
                    else:
                        result = lc_tool.invoke(targs)
                    result_str = str(result)
                except Exception as e:
                    result_str = f"Error executing tool '{tname}': {str(e)}"
            else:
                result_str = f"Error: Tool '{tname}' is not registered."

            new_messages.append(ToolMessage(content=result_str, tool_call_id=call_id, name=tname))
            new_steps.append({
                "tool": tname,
                "server": "Official GitHub MCP Server",
                "arguments": targs,
                "result": result_str
            })

        return {
            "messages": new_messages,
            "tool_steps": new_steps
        }

    async def run(self, user_input: str, history: List[Any] = None) -> Dict[str, Any]:
        messages = history or []
        messages.append(HumanMessage(content=user_input))
        initial_state = {"messages": messages, "tool_steps": []}
        final_state = await self.graph.ainvoke(initial_state)
        return final_state
