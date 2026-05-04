import subprocess
from tool import Tool, ToolResult


class GrepTool(Tool):
    is_read_only = True
    is_concurrency_safe = True
    is_destructive = False

    @property
    def name(self): return "grep"

    @property
    def description(self):
        return (
            "Search file contents using ripgrep. Supports regex patterns. "
            "Use glob to filter file types. Returns matching lines with file and line number."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "File or directory to search (default: current dir)"},
                "glob": {"type": "string", "description": "File glob filter, e.g. '*.py'"},
                "case_insensitive": {"type": "boolean", "description": "Case insensitive search"},
                "context": {"type": "integer", "description": "Lines of context around each match"},
            },
            "required": ["pattern"],
        }

    def call(self, input: dict) -> ToolResult:
        pattern = input["pattern"]
        path = input.get("path", ".")
        glob_filter = input.get("glob")
        case_insensitive = input.get("case_insensitive", False)
        context = input.get("context", 0)

        cmd = ["rg", "--line-number", "--no-heading"]
        if case_insensitive:
            cmd.append("-i")
        if context:
            cmd += ["-C", str(context)]
        if glob_filter:
            cmd += ["-g", glob_filter]
        cmd += [pattern, path]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 1:
                return ToolResult(output="No matches found.")
            if result.returncode > 1:
                return ToolResult(output=result.stderr or "grep error", error=True)
            output = result.stdout.strip()
            lines = output.count("\n") + 1
            if lines > 200:
                output = "\n".join(output.split("\n")[:200]) + f"\n... (truncated, {lines} total matches)"
            return ToolResult(output=output)
        except FileNotFoundError:
            return ToolResult(output="ripgrep (rg) not found. Install with: sudo apt install ripgrep", error=True)
        except Exception as e:
            return ToolResult(output=str(e), error=True)
