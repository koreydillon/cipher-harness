import os
import json
from datetime import datetime


class UndoStack:
    def __init__(self, cwd: str):
        self.cwd = cwd
        self._dir = os.path.join(cwd, ".cipher")
        self._path = os.path.join(self._dir, "undo_stack.json")
        os.makedirs(self._dir, exist_ok=True)
        self._stack: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self):
        with open(self._path, "w") as f:
            json.dump(self._stack, f, indent=2)

    def push(self, path: str, old_content: str):
        self._stack.append({
            "path": path,
            "old_content": old_content,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def pop(self) -> tuple[str, str] | None:
        if not self._stack:
            return None
        entry = self._stack.pop()
        self._save()
        return entry["path"], entry["old_content"]

    def undo_last(self) -> str:
        result = self.pop()
        if result is None:
            return "Nothing to undo."
        path, old_content = result
        try:
            with open(path, "w") as f:
                f.write(old_content)
            return f"Restored: {path}"
        except Exception as e:
            return f"Undo failed for {path}: {e}"

    def list_stack(self) -> list[dict]:
        return list(reversed(self._stack))
