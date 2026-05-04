import os
import sys
import difflib
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tool import Tool, ToolResult

try:
    from rich.console import Console
    from rich.text import Text
    _console = Console()
    _has_rich = True
except ImportError:
    _has_rich = False


def _print_diff(path: str, old: str, new: str):
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))

    if not diff:
        return

    if _has_rich:
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                _console.print(line, style="bold white", end="")
            elif line.startswith("@@"):
                _console.print(line, style="cyan", end="")
            elif line.startswith("+"):
                _console.print(line, style="green", end="")
            elif line.startswith("-"):
                _console.print(line, style="red", end="")
            else:
                print(line, end="")
        print()
    else:
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                print(f"\033[92m{line}\033[0m", end="")
            elif line.startswith("-") and not line.startswith("---"):
                print(f"\033[91m{line}\033[0m", end="")
            else:
                print(line, end="")
        print()


class EditTool(Tool):
    is_read_only = False
    is_concurrency_safe = False
    is_destructive = False

    # Injected by agent after construction
    undo_stack: Any = None

    @property
    def name(self): return "edit"

    @property
    def description(self):
        return (
            "Edit a file by replacing an exact string with a new string. "
            "Fails if old_string is not found or not unique (use replace_all=true to replace all occurrences). "
            "Always read the file first to get the exact text to replace."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "old_string": {"type": "string", "description": "Exact string to find and replace"},
                "new_string": {"type": "string", "description": "String to replace it with"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences (default: false)"},
            },
            "required": ["path", "old_string", "new_string"],
        }

    def call(self, input: dict) -> ToolResult:
        path = os.path.expanduser(input["path"])
        old_string = input["old_string"]
        new_string = input["new_string"]
        replace_all = input.get("replace_all", False)

        if not os.path.exists(path):
            return ToolResult(output=f"File not found: {path}", error=True)
        if not os.path.isfile(path):
            return ToolResult(output=f"Not a file: {path}", error=True)

        try:
            with open(path, "r", errors="replace") as f:
                original = f.read()
        except Exception as e:
            return ToolResult(output=str(e), error=True)

        count = original.count(old_string)
        if count == 0:
            return ToolResult(output=f"old_string not found in {path}", error=True)
        if count > 1 and not replace_all:
            return ToolResult(
                output=f"old_string found {count} times in {path}. Use replace_all=true or provide more context to make it unique.",
                error=True,
            )

        if self.undo_stack is not None:
            self.undo_stack.push(path, original)

        if replace_all:
            updated = original.replace(old_string, new_string)
        else:
            updated = original.replace(old_string, new_string, 1)

        try:
            with open(path, "w") as f:
                f.write(updated)
        except Exception as e:
            return ToolResult(output=str(e), error=True)

        _print_diff(path, original, updated)

        replacements = original.count(old_string) if replace_all else 1
        return ToolResult(output=f"Edited {path} ({replacements} replacement{'s' if replacements != 1 else ''})")
