import os
from tool import Tool, ToolResult


class ReadTool(Tool):
    is_read_only = True
    is_concurrency_safe = True
    is_destructive = False

    @property
    def name(self): return "read"

    @property
    def description(self):
        return (
            "Read a file from the filesystem. Returns the file contents with line numbers. "
            "Use offset and limit to read specific sections of large files."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path to the file"},
                "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)"},
                "limit": {"type": "integer", "description": "Number of lines to read"},
            },
            "required": ["path"],
        }

    def call(self, input: dict) -> ToolResult:
        path = os.path.expanduser(input["path"])
        offset = input.get("offset", 1)
        limit = input.get("limit", None)

        if not os.path.exists(path):
            return ToolResult(output=f"File not found: {path}", error=True)
        if not os.path.isfile(path):
            return ToolResult(output=f"Not a file: {path}", error=True)

        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()

            start = max(0, offset - 1)
            end = start + limit if limit else len(lines)
            selected = lines[start:end]

            numbered = "".join(f"{start + i + 1}\t{line}" for i, line in enumerate(selected))
            return ToolResult(output=numbered or "(empty file)")
        except Exception as e:
            return ToolResult(output=str(e), error=True)
