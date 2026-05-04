import os
import difflib
from tool import Tool, ToolResult


class WriteTool(Tool):
    is_read_only = False
    is_concurrency_safe = False
    is_destructive = True

    def __init__(self):
        super().__init__()
        self.autonomous_mode = False  # Set by agent

    @property
    def name(self): return "write"

    @property
    def description(self):
        return (
            "Write content to a file, creating it if it doesn't exist or overwriting it. "
            "For editing existing files, prefer the edit tool to avoid full rewrites. "
            "Always use absolute paths."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file to write"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        }

    def call(self, input: dict) -> ToolResult:
        path = os.path.expanduser(input["path"])
        content = input["content"]

        # If overwriting an existing file, show diff and confirm
        if os.path.exists(path) and not self.autonomous_mode:
            try:
                with open(path, "r", errors="replace") as f:
                    old_content = f.read()

                if old_content.strip() != content.strip():
                    old_lines = old_content.splitlines(keepends=True)
                    new_lines = content.splitlines(keepends=True)
                    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"old/{os.path.basename(path)}", tofile=f"new/{os.path.basename(path)}"))

                    if diff:
                        print(f"\n\033[93m  ⚠ Overwriting existing file: {path}\033[0m")
                        # Show compact diff
                        shown = 0
                        for line in diff[:20]:
                            if line.startswith("+") and not line.startswith("+++"):
                                print(f"\033[92m  {line}\033[0m", end="")
                                shown += 1
                            elif line.startswith("-") and not line.startswith("---"):
                                print(f"\033[91m  {line}\033[0m", end="")
                                shown += 1
                        if len(diff) > 20:
                            print(f"\033[90m  ... {len(diff) - 20} more diff lines\033[0m")

                        try:
                            confirm = input_func(f"\033[93m  Allow overwrite? (y/n): \033[0m").strip().lower()
                        except (KeyboardInterrupt, EOFError):
                            return ToolResult(output="User cancelled file overwrite.", error=True)
                        if confirm != "y":
                            return ToolResult(output="User denied file overwrite.", error=True)
            except Exception:
                pass  # If we can't read the old file, just write

        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            lines = content.count("\n") + 1
            return ToolResult(output=f"Wrote {lines} lines to {path}")
        except Exception as e:
            return ToolResult(output=str(e), error=True)


# Allow monkey-patching for tests
input_func = input
