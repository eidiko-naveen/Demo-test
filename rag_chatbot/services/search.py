import json
import logging
from dataclasses import dataclass
from typing import Protocol
from urllib import parse, request

from config.settings import get_settings


logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    excerpt: str
    url: str | None = None


class SearchProvider(Protocol):
    def search(self, query: str) -> list[SearchResult]: ...


class DisabledSearchProvider:
    enabled = False

    def search(self, query: str) -> list[SearchResult]:
        logger.info("External search is disabled; using internal knowledge only")
        return []


class DuckDuckGoSearchProvider:
    enabled = True

    def __init__(self, timeout: int | None = None, max_results: int | None = None):
        settings = get_settings()
        self.timeout = timeout if timeout is not None else settings.external_search_timeout
        self.max_results = max_results if max_results is not None else settings.external_search_max_results

    def search(self, query: str) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        params = {
            "q": query.strip(),
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        if get_settings().external_search_country:
            params["kl"] = get_settings().external_search_country
        url = "https://api.duckduckgo.com/?" + parse.urlencode(params)
        try:
            with request.urlopen(url, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("external search failed: %s", type(exc).__name__)
            return []

        results: list[SearchResult] = []
        abstract = payload.get("AbstractText")
        abstract_url = payload.get("AbstractURL")
        if abstract:
            results.append(SearchResult(title=payload.get("Heading") or "Search result", excerpt=abstract, url=abstract_url))

        for item in payload.get("RelatedTopics", [])[: self.max_results]:
            if isinstance(item, dict):
                title = item.get("Text") or item.get("Name") or "Search result"
                url = item.get("FirstURL") or item.get("URL")
                excerpt = item.get("Text") or item.get("Result") or ""
                if url and excerpt:
                    results.append(SearchResult(title=title, excerpt=excerpt, url=url))
                elif isinstance(item.get("Topics"), list):
                    for nested in item["Topics"][: self.max_results]:
                        title = nested.get("Text") or nested.get("Name") or "Search result"
                        url = nested.get("FirstURL") or nested.get("URL")
                        excerpt = nested.get("Text") or nested.get("Result") or ""
                        if url and excerpt:
                            results.append(SearchResult(title=title, excerpt=excerpt, url=url))
                            break

        unique: list[SearchResult] = []
        seen: set[str] = set()
        for result in results[: self.max_results]:
            key = (result.title, result.url or result.excerpt)
            if key in seen:
                continue
            seen.add(key)
            unique.append(result)
        return unique


def get_search_provider() -> SearchProvider:
    settings = get_settings()
    provider_name = (settings.external_search_provider or "").strip().lower()
    if provider_name in {"", "disabled", "none"}:
        return DisabledSearchProvider()
    if provider_name in {"duckduckgo", "ddg"}:
        return DuckDuckGoSearchProvider()
    logger.warning("unknown external_search_provider=%s; falling back to disabled search provider", provider_name)
    return DisabledSearchProvider()