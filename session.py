import os
import shutil
from datetime import datetime


class SessionLogger:
    def __init__(self, cwd: str):
        sessions_dir = os.path.join(cwd, ".cipher", "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._path = os.path.join(sessions_dir, f"{timestamp}.md")
        with open(self._path, "w") as f:
            f.write(f"# Cipher Session — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    def _write(self, text: str):
        with open(self._path, "a") as f:
            f.write(text)

    def log_user(self, msg: str):
        self._write(f"## User\n{msg}\n\n")

    def log_assistant(self, msg: str):
        if msg:
            self._write(f"## Cipher\n{msg}\n\n")

    def log_tool_use(self, name: str, input: dict):
        import json
        self._write(f"### Tool: `{name}`\n```json\n{json.dumps(input, indent=2)}\n```\n\n")

    def log_tool_result(self, name: str, output: str, error: bool = False):
        status = "ERROR" if error else "OK"
        preview = output[:500] + ("..." if len(output) > 500 else "")
        self._write(f"**Result [{status}]:** `{name}`\n```\n{preview}\n```\n\n")

    def export(self, path: str):
        dest = os.path.expanduser(path)
        shutil.copy2(self._path, dest)
        return dest

    @property
    def path(self) -> str:
        return self._path
