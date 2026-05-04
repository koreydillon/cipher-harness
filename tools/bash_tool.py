import re
import subprocess
from tool import Tool, ToolResult


class BashTool(Tool):
    is_read_only = False
    is_concurrency_safe = False
    is_destructive = True

    # Hard-blocked — never allowed
    BLOCKED = [
        "rm -rf /", ":(){ :|:& };:", "mkfs", "dd if=/dev/zero",
        "chmod -R 777 /", "> /dev/sda",
    ]

    # Dangerous patterns that require confirmation (unless autonomous mode)
    DANGEROUS_PATTERNS = [
        (r"rm\s+(-[rfR]+\s+|.*--no-preserve-root)", "recursive delete"),
        (r"git\s+push\s+.*--force", "force push"),
        (r"git\s+reset\s+--hard", "hard reset — destroys uncommitted work"),
        (r"git\s+clean\s+-[dfx]", "git clean — deletes untracked files"),
        (r"DROP\s+(TABLE|DATABASE|SCHEMA)", "DROP statement — destroys data"),
        (r"TRUNCATE\s+TABLE", "TRUNCATE — deletes all rows"),
        (r"DELETE\s+FROM\s+\w+\s*;?\s*$", "DELETE without WHERE — deletes all rows"),
        (r"ALTER\s+TABLE.*DROP\s+COLUMN", "DROP COLUMN — irreversible schema change"),
        (r"kill\s+-9", "force kill process"),
        (r"sudo\s+rm", "sudo rm — elevated delete"),
        (r">\s*/etc/", "overwriting system config"),
        (r"curl.*\|\s*(sudo\s+)?bash", "pipe remote script to bash"),
        (r"wget.*\|\s*(sudo\s+)?bash", "pipe remote script to bash"),
    ]

    # Secrets patterns — warn if about to commit/push/echo these
    SECRET_PATTERNS = [
        r"(ANTHROPIC_API_KEY|OPENAI_API_KEY|STRIPE_SECRET|AWS_SECRET|DATABASE_URL|DB_PASSWORD)",
        r"sk-ant-[a-zA-Z0-9]+",
        r"sk-[a-zA-Z0-9]{20,}",
    ]

    def __init__(self):
        super().__init__()
        self.autonomous_mode = False  # Set by agent

    @property
    def name(self): return "bash"

    @property
    def description(self):
        return (
            "Run a bash command in the current working directory. "
            "Use for file operations, running tests, git commands, installs, etc. "
            "Prefer targeted commands over broad destructive ones. "
            "Avoid interactive commands that require user input."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)", "default": 120},
            },
            "required": ["command"],
        }

    def check_permissions(self, input: dict) -> tuple[bool, str]:
        cmd = input.get("command", "")

        # Hard block
        for blocked in self.BLOCKED:
            if blocked in cmd:
                return False, f"Blocked dangerous pattern: '{blocked}'"

        # Secret leak check
        for pat in self.SECRET_PATTERNS:
            if re.search(pat, cmd) and any(kw in cmd for kw in ["echo", "print", "git add", "git commit", "curl"]):
                return False, f"Blocked: command may leak secrets"

        return True, ""

    def _check_dangerous(self, cmd: str) -> str | None:
        """Return a warning string if the command is dangerous, None if safe."""
        for pattern, description in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return description
        return None

    def call(self, input: dict) -> ToolResult:
        cmd = input["command"]
        timeout = input.get("timeout", 120)

        allowed, reason = self.check_permissions(input)
        if not allowed:
            return ToolResult(output=f"Permission denied: {reason}", error=True)

        # Dangerous command confirmation
        danger = self._check_dangerous(cmd)
        if danger and not self.autonomous_mode:
            print(f"\n\033[93m  ⚠ Dangerous: {danger}\033[0m")
            print(f"\033[93m  Command: {cmd}\033[0m")
            try:
                confirm = input_func(f"\033[93m  Allow? (y/n): \033[0m").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return ToolResult(output="User cancelled dangerous command.", error=True)
            if confirm != "y":
                return ToolResult(output="User denied dangerous command.", error=True)

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.returncode != 0:
                output = result.stderr or result.stdout or f"Exit code {result.returncode}"
                return ToolResult(output=output, error=True)
            return ToolResult(output=output or "(no output)")
        except subprocess.TimeoutExpired:
            return ToolResult(output=f"Command timed out after {timeout}s", error=True)
        except Exception as e:
            return ToolResult(output=str(e), error=True)


# Allow monkey-patching for tests
input_func = input
