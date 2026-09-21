from app.graph.edges import execution_route
from app.graph.nodes.routing import route_agent, set_route, understand_query


def test_explicit_agent_selection_has_priority() -> None:
    state = {"agent_type": "rag", "query": "Compare this with the latest industry practice"}

    state = understand_query(state)

    assert route_agent(state) == "rag"
    assert set_route(state)["route"] == "rag"


def test_hybrid_selection_routes_to_hybrid() -> None:
    state = set_route({"agent_type": "hybrid", "query": "Compare company policy with current practice"})

    assert execution_route(state) == "hybrid"
