from app.research.base import ResearchTool


class ToolRegistry:
    def __init__(self, tools: list[ResearchTool] | None = None):
        self._tools = {tool.name: tool for tool in (tools or []) if hasattr(tool, "name")}

    def register(self, name: str, tool: ResearchTool) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> ResearchTool:
        return self._tools[name]
