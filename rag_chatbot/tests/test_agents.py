import json
from unittest.mock import MagicMock, patch

from agents.router import AgentMode, run_agent
from services.search import DuckDuckGoSearchProvider


def test_hybrid_marks_external_provider_when_unconfigured():
    with patch("agents.router.retrieve_evidence", return_value={"context": "internal", "sources": [{"file": "x"}], "sufficient": True}), \
         patch("agents.router.get_llm") as get_llm:
        get_llm.return_value.complete.return_value = type("Response", (), {"text": "answer"})()
        answer = run_agent(AgentMode.HYBRID, "question", "")
    assert answer.answer.startswith("answer\nSources:")
    prompt = get_llm.return_value.complete.call_args.args[0]
    assert "No external research provider is configured" in prompt
    assert "untrusted evidence" in prompt


def test_research_uses_external_sources():
    provider = MagicMock()
    provider.enabled = True
    provider.search.return_value = [{"title": "t", "excerpt": "e", "url": "u"}]
    with patch("agents.router.retrieve_evidence", return_value={"context": "internal", "sources": [{"file": "x"}], "sufficient": True}), \
         patch("agents.router.get_search_provider", return_value=provider), \
         patch("agents.router.get_llm") as get_llm:
        get_llm.return_value.complete.return_value = type("Response", (), {"text": "answer"})()
        run_agent(AgentMode.RESEARCH, "question", "")
    provider.search.assert_called_once_with("question")


def test_duckduckgo_search_provider_parses_results():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self):
            return json.dumps({
                "AbstractText": "summary",
                "Heading": "Example",
                "AbstractURL": "https://example.com",
                "RelatedTopics": [{"Text": "Search result", "FirstURL": "https://example.com/result"}],
            }).encode("utf-8")

    with patch("services.search.get_settings", return_value=type("Settings", (), {"external_search_timeout": 5, "external_search_max_results": 5, "external_search_country": None})()), \
         patch("services.search.request.urlopen", return_value=FakeResponse()):
        results = DuckDuckGoSearchProvider().search("hello world")
    assert results[0].title == "Example"
    assert results[0].excerpt == "summary"
    assert any(item.url == "https://example.com/result" for item in results)
