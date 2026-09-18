from unittest.mock import patch

from agents.router import AgentMode, run_agent


def test_insufficient_evidence_abstains_before_llm_call():
    with patch("agents.router.retrieve_evidence", return_value={"context": "", "sources": [], "sufficient": False}), \
         patch("agents.router.get_llm") as get_llm:
        result = run_agent(AgentMode.RAG, "unknown", "")
    assert "sufficient information" in result.answer
    get_llm.assert_not_called()