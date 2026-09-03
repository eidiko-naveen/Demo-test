import asyncio
from agent.graph import EidikoAgentWorkflow
from mcp_client.sse_aggregator import SseAggregator

def test_agent_run():
    aggregator = SseAggregator()
    agent = EidikoAgentWorkflow(aggregator)
    result = asyncio.run(agent.run("Create a repository named 'eidiko-test-agent' and notify leadership via email."))
    assert "messages" in result
    assert len(result["messages"]) > 0
