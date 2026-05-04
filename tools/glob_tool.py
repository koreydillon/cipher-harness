import glob as glob_module
import os
from tool import Tool, ToolResult


class GlobTool(Tool):
    is_read_only = True
    is_concurrency_safe = True
    is_destructive = False

    @property
    def name(self): return "glob"

    @property
    def description(self):
        return (
            "Find files by glob pattern. Returns matching paths sorted by modification time. "
            "Examples: '**/*.py', 'src/**/*.ts', '*.json'"
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern to match files"},
                "path": {"type": "string", "description": "Directory to search in (default: current directory)"},
            },
            "required": ["pattern"],
        }

    def call(self, input: dict) -> ToolResult:
        pattern = input["pattern"]
        base = os.path.expanduser(input.get("path", "."))

        full_pattern = os.path.join(base, pattern)
        try:
            matches = glob_module.glob(full_pattern, recursive=True)
            matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            if not matches:
                return ToolResult(output="No files matched.")
            return ToolResult(output="\n".join(matches))
        except Exception as e:
            return ToolResult(output=str(e), error=True)
