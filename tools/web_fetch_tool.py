import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tool import Tool, ToolResult


class WebFetchTool(Tool):
    is_read_only = True
    is_concurrency_safe = True
    is_destructive = False

    @property
    def name(self): return "web_fetch"

    @property
    def description(self):
        return (
            "Fetch a web page and return its readable text content. "
            "Optionally use a CSS selector to extract specific content. "
            "Strips scripts and styles automatically."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "selector": {"type": "string", "description": "CSS selector to extract specific content (optional)"},
                "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)"},
            },
            "required": ["url"],
        }

    def call(self, input: dict) -> ToolResult:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as e:
            return ToolResult(output=f"Missing dependency: {e}. Install with: pip install requests beautifulsoup4", error=True)

        url = input["url"]
        selector = input.get("selector")
        max_chars = input.get("max_chars", 8000)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Cipher/1.0; +https://github.com/koreydillon/cipher-harness)"
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as e:
            return ToolResult(output=f"Fetch failed: {e}", error=True)

        try:
            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                tag.decompose()

            if selector:
                elements = soup.select(selector)
                if not elements:
                    # Fall back to full page
                    text = soup.get_text(separator="\n", strip=True)
                    prefix = f"[selector '{selector}' not found — showing full page]\n\n"
                else:
                    text = "\n\n".join(el.get_text(separator="\n", strip=True) for el in elements)
                    prefix = f"[selector: {selector}]\n\n"
            else:
                text = soup.get_text(separator="\n", strip=True)
                prefix = ""

            # Collapse excessive blank lines
            import re
            text = re.sub(r"\n{3,}", "\n\n", text).strip()

            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... (truncated at {max_chars} chars)"

            return ToolResult(output=prefix + text)
        except Exception as e:
            return ToolResult(output=f"Parse error: {e}", error=True)
