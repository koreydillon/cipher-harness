import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tool import Tool, ToolResult

STATUS_ICONS = {
    "pending": "⬜",
    "in_progress": "🔄",
    "done": "✅",
}


class TaskTool(Tool):
    is_read_only = False
    is_concurrency_safe = False
    is_destructive = False

    def __init__(self, cwd: str | None = None):
        self.cwd = cwd or os.getcwd()

    @property
    def name(self): return "task"

    @property
    def description(self):
        return (
            "Manage a task list for the current project. "
            "Actions: create (takes tasks list), list, update (set status), complete, clear."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "update", "complete", "clear"],
                    "description": "Action to perform",
                },
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task descriptions (for 'create')",
                },
                "task_id": {
                    "type": "integer",
                    "description": "Task ID (for 'update' or 'complete')",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done"],
                    "description": "New status (for 'update')",
                },
            },
            "required": ["action"],
        }

    def _tasks_path(self) -> str:
        return os.path.join(self.cwd, ".cipher", "tasks.json")

    def _load(self) -> list[dict]:
        path = self._tasks_path()
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self, tasks: list[dict]):
        path = self._tasks_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(tasks, f, indent=2)

    def _format_list(self, tasks: list[dict]) -> str:
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            icon = STATUS_ICONS.get(t["status"], "?")
            lines.append(f"  [{t['id']}] {icon} {t['description']}  ({t['status']})")
        return "\n".join(lines)

    def call(self, input: dict) -> ToolResult:
        action = input["action"]
        tasks = self._load()

        if action == "create":
            new_tasks = input.get("tasks", [])
            if not new_tasks:
                return ToolResult(output="No tasks provided.", error=True)
            next_id = max((t["id"] for t in tasks), default=0) + 1
            for desc in new_tasks:
                tasks.append({
                    "id": next_id,
                    "description": desc,
                    "status": "pending",
                    "created": datetime.now().isoformat(),
                })
                next_id += 1
            self._save(tasks)
            return ToolResult(output=f"Created {len(new_tasks)} task(s).\n\n" + self._format_list(tasks))

        elif action == "list":
            return ToolResult(output=self._format_list(tasks))

        elif action == "update":
            task_id = input.get("task_id")
            status = input.get("status")
            if task_id is None or not status:
                return ToolResult(output="task_id and status required for update.", error=True)
            for t in tasks:
                if t["id"] == task_id:
                    t["status"] = status
                    self._save(tasks)
                    return ToolResult(output=f"Task {task_id} → {status}\n\n" + self._format_list(tasks))
            return ToolResult(output=f"Task {task_id} not found.", error=True)

        elif action == "complete":
            task_id = input.get("task_id")
            if task_id is None:
                return ToolResult(output="task_id required for complete.", error=True)
            for t in tasks:
                if t["id"] == task_id:
                    t["status"] = "done"
                    self._save(tasks)
                    return ToolResult(output=f"Task {task_id} marked done.\n\n" + self._format_list(tasks))
            return ToolResult(output=f"Task {task_id} not found.", error=True)

        elif action == "clear":
            self._save([])
            return ToolResult(output="All tasks cleared.")

        return ToolResult(output=f"Unknown action: {action}", error=True)
