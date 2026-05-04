"""
Agent tool for Cipher — spawns sub-agents to handle tasks in parallel.
Like Claude Code's Agent tool, this lets Cipher delegate work to worker agents
that run concurrently and report back results.
"""
import os
import sys
import json
import threading
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tool import Tool, ToolResult


class AgentTool(Tool):
    is_read_only = False
    is_concurrency_safe = True
    is_destructive = False

    def __init__(self, parent_agent=None):
        super().__init__()
        self._parent = parent_agent
        self._workers: dict[str, dict] = {}  # id -> {thread, result, status}
        self._counter = 0

    @property
    def name(self): return "agent"

    @property
    def description(self):
        return (
            "Spawn a sub-agent to handle a task independently. Sub-agents get their own context "
            "and can use all tools. Use this to parallelize work — e.g., 'research this while I fix that'. "
            "Actions: 'spawn' creates a new agent with a task, 'check' gets its status/result, "
            "'list' shows all running agents."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["spawn", "check", "list"],
                    "description": "spawn: create a new sub-agent, check: get result by id, list: show all agents",
                },
                "task": {"type": "string", "description": "Task description for the sub-agent (for spawn)"},
                "agent_id": {"type": "string", "description": "Agent ID to check (for check)"},
            },
            "required": ["action"],
        }

    def call(self, input: dict) -> ToolResult:
        action = input["action"]

        if action == "spawn":
            task = input.get("task", "")
            if not task:
                return ToolResult(output="'task' is required for spawn", error=True)
            return self._spawn(task)
        elif action == "check":
            agent_id = input.get("agent_id", "")
            if not agent_id:
                return ToolResult(output="'agent_id' is required for check", error=True)
            return self._check(agent_id)
        elif action == "list":
            return self._list()
        else:
            return ToolResult(output=f"Unknown action: {action}", error=True)

    def _spawn(self, task: str) -> ToolResult:
        if self._parent is None:
            return ToolResult(output="No parent agent — cannot spawn sub-agent", error=True)

        self._counter += 1
        agent_id = f"agent-{self._counter}"

        worker = {
            "id": agent_id,
            "task": task,
            "status": "running",
            "result": None,
            "started": time.time(),
        }
        self._workers[agent_id] = worker

        # Run the sub-agent in a background thread
        thread = threading.Thread(
            target=self._run_worker,
            args=(agent_id, task),
            daemon=True,
        )
        worker["thread"] = thread
        thread.start()

        return ToolResult(
            output=f"Spawned {agent_id}: {task[:80]}\nUse agent(action='check', agent_id='{agent_id}') to get the result."
        )

    def _run_worker(self, agent_id: str, task: str):
        """Run a sub-agent in a separate thread."""
        try:
            # Create a branched agent for isolation
            sub = self._parent.branch()
            result = sub.run(task)
            self._workers[agent_id]["result"] = result
            self._workers[agent_id]["status"] = "done"
        except Exception as e:
            self._workers[agent_id]["result"] = f"Error: {e}"
            self._workers[agent_id]["status"] = "error"

    def _check(self, agent_id: str) -> ToolResult:
        worker = self._workers.get(agent_id)
        if not worker:
            return ToolResult(output=f"No agent found with id: {agent_id}", error=True)

        elapsed = time.time() - worker["started"]

        if worker["status"] == "running":
            return ToolResult(output=f"{agent_id} still running ({elapsed:.0f}s elapsed). Check again later.")

        result = worker["result"] or "(no output)"
        status = worker["status"]
        return ToolResult(
            output=f"{agent_id} [{status}] ({elapsed:.1f}s)\nTask: {worker['task'][:80]}\n\nResult:\n{result}"
        )

    def _list(self) -> ToolResult:
        if not self._workers:
            return ToolResult(output="No sub-agents spawned yet.")

        lines = ["Sub-agents:", ""]
        for wid, w in self._workers.items():
            elapsed = time.time() - w["started"]
            status_icon = {"running": "⏳", "done": "✅", "error": "❌"}.get(w["status"], "?")
            lines.append(f"  {status_icon} {wid} [{w['status']}] {elapsed:.0f}s — {w['task'][:60]}")

        return ToolResult(output="\n".join(lines))
