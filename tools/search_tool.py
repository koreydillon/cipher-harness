"""
Web search tool for Cipher — searches DuckDuckGo (no API key needed)
and returns summarized results. Lets Cipher look up errors, docs, and solutions.
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tool import Tool, ToolResult


class SearchTool(Tool):
    is_read_only = True
    is_concurrency_safe = True
    is_destructive = False

    @property
    def name(self): return "search"

    @property
    def description(self):
        return (
            "Search the web using DuckDuckGo. Returns top results with titles, URLs, and snippets. "
            "Use this to look up error messages, find documentation, check library versions, "
            "or research solutions. No API key required."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g., 'python requests timeout error', 'fastapi middleware docs')"},
                "max_results": {"type": "integer", "description": "Max results to return (default 5, max 10)"},
            },
            "required": ["query"],
        }

    def call(self, input: dict) -> ToolResult:
        query = input["query"]
        max_results = min(input.get("max_results", 5), 10)

        # Try duckduckgo-search first (best quality)
        result = self._search_ddg(query, max_results)
        if result:
            return result

        # Fallback: scrape DuckDuckGo HTML
        result = self._search_ddg_html(query, max_results)
        if result:
            return result

        return ToolResult(
            output="Search failed. Install duckduckgo-search for best results: pip install duckduckgo-search",
            error=True,
        )

    def _search_ddg(self, query: str, max_results: int) -> ToolResult | None:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return None

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(r)

            if not results:
                return ToolResult(output=f"No results found for: {query}")

            output_lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("href", r.get("link", ""))
                snippet = r.get("body", r.get("snippet", ""))
                output_lines.append(f"{i}. {title}")
                output_lines.append(f"   {url}")
                output_lines.append(f"   {snippet}")
                output_lines.append("")

            return ToolResult(output="\n".join(output_lines))
        except Exception as e:
            return ToolResult(output=f"Search error: {e}", error=True)

    def _search_ddg_html(self, query: str, max_results: int) -> ToolResult | None:
        """Fallback: scrape DuckDuckGo HTML results."""
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            return None

        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; Cipher/1.0)"}
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            results_div = soup.select(".result")

            if not results_div:
                return ToolResult(output=f"No results found for: {query}")

            output_lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results_div[:max_results], 1):
                title_el = r.select_one(".result__title a")
                snippet_el = r.select_one(".result__snippet")

                title = title_el.get_text(strip=True) if title_el else "No title"
                url = title_el.get("href", "") if title_el else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                output_lines.append(f"{i}. {title}")
                if url:
                    output_lines.append(f"   {url}")
                if snippet:
                    output_lines.append(f"   {snippet}")
                output_lines.append("")

            return ToolResult(output="\n".join(output_lines))
        except Exception as e:
            return ToolResult(output=f"HTML search error: {e}", error=True)
