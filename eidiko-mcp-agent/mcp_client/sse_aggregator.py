import asyncio
import os
import concurrent.futures
from typing import List, Dict, Any
from langchain_core.tools import StructuredTool
from pydantic import create_model, Field
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from config import GITHUB_TOKEN

class SseAggregator:
    """
    Official GitHub MCP Aggregator.
    Connects directly to the Official GitHub MCP Docker Container over Stdio,
    discovers all 42 official tools, and exposes them to LangGraph.
    """

    def __init__(self, token: str = None):
        self.github_token = token or os.getenv("GITHUB_TOKEN", GITHUB_TOKEN)
        self.tool_definitions: Dict[str, Dict[str, Any]] = {}
        self.server_health: Dict[str, bool] = {"github": True}

    def _get_server_params(self) -> StdioServerParameters:
        return StdioServerParameters(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "ghcr.io/github/github-mcp-server"
            ],
            env={
                **os.environ,
                "GITHUB_PERSONAL_ACCESS_TOKEN": self.github_token or ""
            }
        )

    def discover_tools_sync(self) -> List[StructuredTool]:
        """Synchronously discover tools from the Official GitHub MCP Server."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(self.discover_tools())).result()
        else:
            return asyncio.run(self.discover_tools())

    async def discover_tools(self) -> List[StructuredTool]:
        """Query the Official GitHub MCP server and return LangChain-compatible tools."""
        self.tool_definitions.clear()
        langchain_tools = []

        params = self._get_server_params()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.list_tools()
                    self.server_health["github"] = True

                    for tool in res.tools:
                        tname = tool.name
                        schema_dict = tool.inputSchema if hasattr(tool, "inputSchema") else {}
                        if hasattr(schema_dict, "model_dump"):
                            schema_dict = schema_dict.model_dump()
                        elif not isinstance(schema_dict, dict):
                            schema_dict = {}

                        self.tool_definitions[tname] = {
                            "description": tool.description or "",
                            "inputSchema": schema_dict
                        }

                        lc_tool = self._create_langchain_tool(tname, tool.description or "", schema_dict)
                        langchain_tools.append(lc_tool)
        except Exception as e:
            self.server_health["github"] = False
            print(f"[Official GitHub MCP Client Warning] Could not connect to GitHub MCP Container: {e}")

        return langchain_tools

    def _create_langchain_tool(self, tool_name: str, description: str, schema_dict: Dict[str, Any]) -> StructuredTool:
        """Dynamically construct a LangChain StructuredTool that calls official MCP session."""
        props = schema_dict.get("properties", {})
        required = schema_dict.get("required", [])

        fields = {}
        for prop_name, prop_info in props.items():
            ptype = str
            tstr = prop_info.get("type", "string")
            if tstr == "integer":
                ptype = int
            elif tstr == "boolean":
                ptype = bool
            elif tstr == "array":
                ptype = list
            elif tstr == "object":
                ptype = dict

            default_val = ... if prop_name in required else prop_info.get("default", None)
            fields[prop_name] = (ptype, Field(default=default_val, description=prop_info.get("description", "")))

        args_model = create_model(f"{tool_name}_input", **fields)

        def _sync_func(**kwargs):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(self.execute_tool(tool_name, kwargs))).result()
            else:
                return asyncio.run(self.execute_tool(tool_name, kwargs))

        async def _async_func(**kwargs):
            return await self.execute_tool(tool_name, kwargs)

        return StructuredTool.from_function(
            func=_sync_func,
            coroutine=_async_func,
            name=tool_name,
            description=description or f"Official GitHub MCP Tool {tool_name}",
            args_schema=args_model
        )

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Call official tool on the GitHub MCP server via stdio container context."""
        params = self._get_server_params()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool(tool_name, tool_args)
                    texts = [item.text for item in res.content if hasattr(item, "text")]
                    return "\n".join(texts) if texts else "Tool executed successfully with no text output."
        except Exception as e:
            return f"Error executing tool '{tool_name}' on Official GitHub MCP Server: {str(e)}"
