"""
Cipher Agent Loop — enhanced with memory, cost tracking, session logging, undo, plugins, and auto-compact.
"""
import sys
import json
import os
import copy
import random
import threading
import time
from typing import Any
import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from local_client import get_client

from tool import Tool, ToolResult
from tools.bash_tool import BashTool
from tools.read_tool import ReadTool
from tools.write_tool import WriteTool
from tools.glob_tool import GlobTool
from tools.grep_tool import GrepTool
from tools.edit_tool import EditTool
from tools.web_fetch_tool import WebFetchTool
from tools.search_tool import SearchTool
from tools.codebase_tool import CodebaseTool
from tools.task_tool import TaskTool
from tools.agent_tool import AgentTool
from tools.self_extend_tool import SelfExtendTool

from memory import load_memory
from compact import should_compact, compact_messages
from cost_tracker import CostTracker
from session import SessionLogger
from plugins import load_plugins
from project_scanner import scan_project
from undo import UndoStack

from config import cfg  # noqa: E402  (import after sys.path patch above)

MODEL = cfg.model
MAX_TOKENS = cfg.max_tokens
PLUGIN_DIR = cfg.plugin_dir

BASE_SYSTEM_PROMPT = """You are Cipher, an expert coding agent. You DO things — you don't explain how to do them. You're sharp, confident, and a little casual — like a senior dev pair-programming with a friend.

CRITICAL RULES:
1. ALWAYS use your tools to take action. NEVER paste code to the user. Use the write tool to create files, bash tool to run commands, edit tool to modify files.
2. When asked to build something, BUILD IT. Don't ask questions, don't give tutorials, don't explain steps. Just start writing files and running commands.
3. NEVER output raw JSON, tool schemas, or function signatures to the user. Speak in plain english only.
4. After building something, tell the user how to run it in one short sentence.
5. NEVER stop after a single tool call. Keep calling tools until the task is FULLY COMPLETE. If you need to create 3 files, create all 3 without stopping. Only stop when there is nothing left to do.
6. Do NOT ask for permission. Just do it. Never say "shall I" or "would you like me to" — just act.

You have access to tools: bash, read, write, edit, glob, grep, web_fetch, search, codebase, task, agent, self_extend.

## When to use sub-agents
- Use the agent tool to spawn sub-agents for independent parallel tasks
- Example: "spawn one agent to research the bug and another to write tests"
- Check on agents with agent(action='check', agent_id='agent-1')
- Don't spawn agents for simple sequential work — just do it yourself

## How to communicate
- Be conversational and natural. Talk like a real person working alongside them.
- WHILE WORKING, give brief status comments before each tool call:
  "Let me check what's in here..." (before read)
  "Alright, writing that up now..." (before write)
  "Hmm, let me find where that lives..." (before grep/glob)
  "Running it to see if that worked..." (before bash test)
  "One sec, fixing that..." (before edit)
- Show your thinking: "This looks like a path issue — let me grep for it"
- Celebrate wins: "Boom — snake game is ready. Run it with: python3 snake.py"
- When something's tricky: "Interesting — this is more tangled than it looks"
- On errors: "Ah, that didn't work. Let me try it differently..."
- Use short, punchy sentences. Lead with action.
- When the user doesn't interrupt, keep working and provide natural status updates
- NEVER be silent — always say something brief before acting

## Tool guidelines
- Always read files before editing them
- Use edit for targeted changes, write only for new files or complete rewrites
- Run tests after making changes
- Never guess file paths — use glob or grep to find them first
- Use the task tool to track complex multi-step work

## Git safety
- Stage specific files by name — NEVER use git add -A or git add .
- Write descriptive commit messages
- NEVER force push, hard reset, or rebase without asking
- Check git status before committing to avoid staging secrets (.env, credentials, keys)
- If you see .env or credential files staged, UNSTAGE them immediately

## Database safety
- ALWAYS run SELECT before UPDATE/DELETE to preview affected rows
- NEVER run DELETE FROM without a WHERE clause
- NEVER run DROP TABLE/DATABASE without explicit user approval
- When connecting to a database, identify if it's prod vs dev first
- Back up tables before destructive schema changes: CREATE TABLE backup_X AS SELECT * FROM X

## Planning for complex tasks
When a task involves 3+ files, multiple steps, or could go wrong:
1. FIRST, briefly state your plan: "Here's my approach: 1) ... 2) ... 3) ..."
2. Use the task tool to create a checklist
3. Work through each step, marking tasks complete as you go
4. If a step fails, reassess the plan before continuing

For simple tasks (single file edit, quick lookup), skip planning and just act.
"""

WRITE_TOOL_NAMES = {"write", "edit"}

# Fun status words shown while Cipher is working
CIPHER_VERBS = [
    "ciphering", "doodlebugging", "whatchamacalliting", "thingamajiggling",
    "razzle-dazzling", "brain-wrangling", "code-whispering", "bit-twiddling",
    "pixel-pushing", "bug-squashing", "yak-shaving", "rubber-ducking",
    "turbo-hacking", "wizardifying", "spelunking", "noodling",
    "finagling", "bamboozling the compiler", "tickling the CPU",
    "consulting the oracle", "shaking the magic 8-ball", "decrypting vibes",
    "hotwiring neurons", "wrangling semicolons", "summoning stack traces",
    "defragmenting thoughts", "compiling brilliance", "reverse-engineering chaos",
    "untangling spaghetti", "brewing algorithms", "calibrating the flux capacitor",
    "greasing the gears", "polishing the bits", "juggling pointers",
    "herding electrons", "channeling the matrix", "decoding the universe",
]

def _cipher_verb() -> str:
    return random.choice(CIPHER_VERBS)


class Spinner:
    """Animated spinner shown while Cipher is thinking."""
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = ""):
        self._message = message
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        # Clear the spinner line
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _spin(self):
        i = 0
        while self._running:
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r\033[38;5;93m  {frame} {self._message}\033[0m")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1


MAX_TOOL_RETRIES = 2  # auto-retry failed tool calls this many times


def _format_tool_header(name: str, inputs: dict) -> str:
    """Format tool calls like Claude Code does — clean, human-readable."""
    verb = _cipher_verb()

    if name == "bash":
        cmd = inputs.get("command", "")
        if len(cmd) > 80:
            cmd = cmd[:77] + "..."
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1mbash\033[0m \033[90m$ {cmd}\033[0m"

    elif name == "read":
        path = inputs.get("path", inputs.get("file_path", ""))
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1mread\033[0m \033[90m{path}\033[0m"

    elif name == "write":
        path = inputs.get("path", inputs.get("file_path", ""))
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1mwrite\033[0m \033[90m{path}\033[0m"

    elif name == "edit":
        path = inputs.get("path", inputs.get("file_path", ""))
        old = inputs.get("old_string", inputs.get("old_text", ""))
        new = inputs.get("new_string", inputs.get("new_text", ""))
        header = f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1medit\033[0m \033[90m{path}\033[0m"
        # Show diff-like substitution
        if old and new:
            old_preview = old.strip().split("\n")[0][:60]
            new_preview = new.strip().split("\n")[0][:60]
            header += f"\n\033[91m  - {old_preview}\033[0m"
            header += f"\n\033[92m  + {new_preview}\033[0m"
        return header

    elif name == "glob":
        pattern = inputs.get("pattern", "")
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1mglob\033[0m \033[90m{pattern}\033[0m"

    elif name == "grep":
        pattern = inputs.get("pattern", "")
        path = inputs.get("path", ".")
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1mgrep\033[0m \033[90m/{pattern}/ in {path}\033[0m"

    elif name == "web_fetch":
        url = inputs.get("url", "")
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1mfetch\033[0m \033[90m{url}\033[0m"

    elif name == "task":
        action = inputs.get("action", "")
        desc = inputs.get("description", "")
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1mtask\033[0m \033[90m{action} {desc}\033[0m"

    else:
        return f"\033[38;5;39m  ⏵ {verb}...\033[0m \033[1m{name}\033[0m"


def _format_tool_result(name: str, result: "ToolResult") -> str:
    """Format tool results cleanly — no raw dumps."""
    if result.error:
        return f"\033[91m  ✗ {result.output[:150]}\033[0m"

    output = result.output
    if name == "bash":
        lines = output.strip().split("\n")
        if len(lines) <= 5:
            formatted = "\n".join(f"\033[90m    {l}\033[0m" for l in lines)
        else:
            formatted = "\n".join(f"\033[90m    {l}\033[0m" for l in lines[:3])
            formatted += f"\n\033[90m    ... ({len(lines) - 3} more lines)\033[0m"
        return formatted

    elif name in ("read", "glob", "grep"):
        lines = output.strip().split("\n")
        count = len(lines)
        if count <= 3:
            return "\n".join(f"\033[90m    {l}\033[0m" for l in lines)
        return f"\033[90m    ({count} lines)\033[0m"

    elif name in ("write", "edit"):
        return f"\033[92m  ✓ done\033[0m"

    else:
        preview = output[:80].replace("\n", " ")
        return f"\033[90m    {preview}{'...' if len(output) > 80 else ''}\033[0m"


def build_tools(tool_list: list[Tool]) -> list[dict]:
    return [t.to_api_dict() for t in tool_list]


def partition_tool_calls(calls: list[dict], tool_map: dict[str, Tool]) -> list[list[dict]]:
    batches = []
    current_batch = []

    for call in calls:
        tool = tool_map.get(call["name"])
        if tool and tool.is_concurrency_safe:
            current_batch.append(call)
        else:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append([call])

    if current_batch:
        batches.append(current_batch)

    return batches


def execute_tool(tool: Tool, input: dict) -> ToolResult:
    allowed, reason = tool.check_permissions(input)
    if not allowed:
        return ToolResult(output=f"Permission denied: {reason}", error=True)
    return tool.call(input)


def format_tool_result(tool_use_id: str, result: ToolResult) -> dict:
    content = result.output
    if result.error:
        content = f"[ERROR] {result.output}"
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }


class CipherAgent:
    def __init__(self, api_key: str | None = None, cwd: str | None = None):
        self.client = get_client(api_key)
        self.model = cfg.cipher_model if cfg.local_model else MODEL
        self.cwd = cwd or os.getcwd()
        self.autonomous_mode = False
        self.budget: float | None = None

        # Init support modules
        self.undo_stack = UndoStack(self.cwd)
        self.cost_tracker = CostTracker(self.model)
        self.session_logger = SessionLogger(self.cwd)

        # Build tools
        edit_tool = EditTool()
        edit_tool.undo_stack = self.undo_stack
        self._write_tool = WriteTool()
        self._bash_tool = BashTool()

        # Core tools — keep lightweight for local model performance
        self.tools: list[Tool] = [
            self._bash_tool,
            ReadTool(),
            self._write_tool,
            edit_tool,
            GlobTool(),
            GrepTool(),
        ]

        # Extended tools — loaded only when not using local model
        if not cfg.local_model:
            self.tools.extend([
                WebFetchTool(),
                SearchTool(),
                CodebaseTool(),
                TaskTool(cwd=self.cwd),
                AgentTool(parent_agent=self),
                SelfExtendTool(agent=self),
            ])

        # Load plugins
        plugin_tools = load_plugins(PLUGIN_DIR)
        self.tools.extend(plugin_tools)

        self.tool_map: dict[str, Tool] = {t.name: t for t in self.tools}
        self._api_tools = build_tools(self.tools)

        self.messages: list[dict] = []

        # Build system prompt with project context + memory
        self._project_context = scan_project(self.cwd)
        self._memory_content = load_memory(self.cwd)
        self.system_prompt = self._build_system_prompt()

    def _detect_environment(self) -> str:
        """Detect if we're in prod/staging/dev based on env vars and context."""
        env_hints = []
        # Check common env indicators
        node_env = os.environ.get("NODE_ENV", "")
        rail_env = os.environ.get("RAILS_ENV", "")
        flask_env = os.environ.get("FLASK_ENV", "")
        cipher_env = os.environ.get("CIPHER_ENV", "development")
        database_url = os.environ.get("DATABASE_URL", "")

        if any(e == "production" for e in [node_env, rail_env, flask_env, cipher_env]):
            env_hints.append("⚠️ PRODUCTION ENVIRONMENT DETECTED")
        if database_url and any(h in database_url for h in [".rds.", ".cloud.google", "render.com", "supabase", "neon.tech"]):
            env_hints.append("⚠️ PRODUCTION DATABASE URL DETECTED — be extremely careful with mutations")
        if os.path.exists(os.path.join(self.cwd, ".env")) and not os.path.exists(os.path.join(self.cwd, ".env.example")):
            env_hints.append("Note: .env file found — secrets may be present, never commit or echo them")

        if env_hints:
            return "\n## Environment Warnings\n" + "\n".join(f"- {h}" for h in env_hints)
        return ""

    def _build_system_prompt(self) -> str:
        parts = [BASE_SYSTEM_PROMPT, self._project_context]
        env_warning = self._detect_environment()
        if env_warning:
            parts.append(env_warning)
        memory = load_memory(self.cwd)
        if memory:
            parts.append(f"## Project Memory\n{memory}")
        return "\n\n".join(parts)

    def reset(self):
        self.messages = []

    def switch_model(self, model_name: str):
        aliases = {
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
            "opus": "claude-opus-4-6",
        }
        resolved = aliases.get(model_name.lower(), model_name)
        self.model = resolved
        self.cost_tracker.model = resolved
        print(f"\033[90m[cipher] model → {resolved}\033[0m")

    def branch(self) -> "CipherAgent":
        new_agent = CipherAgent.__new__(CipherAgent)
        new_agent.client = self.client
        new_agent.model = self.model
        new_agent.cwd = self.cwd
        new_agent.autonomous_mode = self.autonomous_mode
        new_agent.budget = self.budget
        new_agent.undo_stack = UndoStack(self.cwd)
        new_agent.cost_tracker = CostTracker(self.model)
        new_agent.session_logger = SessionLogger(self.cwd)
        new_agent.tools = list(self.tools)
        new_agent.tool_map = dict(self.tool_map)
        new_agent._api_tools = list(self._api_tools)
        new_agent.messages = copy.deepcopy(self.messages)
        new_agent._project_context = self._project_context
        new_agent._memory_content = self._memory_content
        new_agent.system_prompt = self.system_prompt
        return new_agent

    def _stream_response(self) -> tuple[str, list[dict], Any]:
        text_parts = []
        tool_uses = []
        usage = None

        # Auto-compact if needed — works for both API and local models
        if should_compact(self.messages, self.model):
            print(f"\033[38;5;93m[cipher] {_cipher_verb()}... (compacting context)\033[0m")
            self.messages = compact_messages(self.client, self.messages, self.model)

        spinner = Spinner(_cipher_verb() + "...")
        spinner.start()

        with self.client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system_prompt,
            tools=self._api_tools,       # type: ignore[arg-type]
            messages=self.messages,      # type: ignore[arg-type]
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        tool_uses.append({
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": {},
                            "_raw_input": "",
                        })

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        spinner.stop()
                        text_parts.append(event.delta.text)
                        print(event.delta.text, end="", flush=True)
                    elif event.delta.type == "input_json_delta":
                        spinner.stop()
                        if tool_uses:
                            tool_uses[-1]["_raw_input"] += event.delta.partial_json

                elif event.type == "content_block_stop":
                    if tool_uses and tool_uses[-1].get("_raw_input"):
                        try:
                            tool_uses[-1]["input"] = json.loads(tool_uses[-1]["_raw_input"])
                        except json.JSONDecodeError:
                            tool_uses[-1]["input"] = {}

            spinner.stop()
            # Get final usage after stream ends
            final_msg = stream.get_final_message()
            if final_msg:
                usage = final_msg.usage

        for t in tool_uses:
            t.pop("_raw_input", None)

        return "".join(text_parts), tool_uses, usage

    def _run_tool_batches(self, tool_uses: list[dict]) -> list[dict]:
        batches = partition_tool_calls(tool_uses, self.tool_map)
        results = []

        for batch in batches:
            for call in batch:
                tool = self.tool_map.get(call["name"])
                if not tool:
                    result = ToolResult(output=f"Unknown tool: {call['name']}", error=True)
                else:
                    print(f"\n{_format_tool_header(call['name'], call['input'])}")
                    self.session_logger.log_tool_use(call["name"], call["input"])

                    # Push to undo stack before write/edit
                    if call["name"] in WRITE_TOOL_NAMES and "path" in call["input"]:
                        path = os.path.expanduser(call["input"]["path"])
                        if os.path.exists(path) and call["name"] == "write":
                            try:
                                with open(path) as f:
                                    old_content = f.read()
                                self.undo_stack.push(path, old_content)
                            except Exception:
                                pass

                    result = execute_tool(tool, call["input"])
                    self.session_logger.log_tool_result(call["name"], result.output, result.error)
                    print(_format_tool_result(call["name"], result))

                results.append(format_tool_result(call["id"], result))

        return results

    def _check_budget(self):
        if self.budget is None:
            return
        cost = self.cost_tracker.session_cost()
        if cost >= self.budget:
            raise RuntimeError(f"Budget limit ${self.budget:.2f} reached (spent ${cost:.3f}). Use /budget to increase.")
        if cost >= self.budget * 0.8:
            pct = cost / self.budget * 100
            print(f"\033[93m[cipher] warning: {pct:.0f}% of budget used (${cost:.3f} / ${self.budget:.2f})\033[0m")

    def run(self, user_message: str) -> str:
        self._check_budget()
        self.messages.append({"role": "user", "content": user_message})
        self.session_logger.log_user(user_message)

        # Refresh system prompt with latest memory
        self.system_prompt = self._build_system_prompt()

        consecutive_errors = 0

        while True:
            text, tool_uses, usage = self._stream_response()

            if usage:
                self.cost_tracker.add_usage(usage.input_tokens, usage.output_tokens)

            # Build assistant message
            assistant_content = []
            if text:
                assistant_content.append({"type": "text", "text": text})
            for call in tool_uses:
                assistant_content.append({
                    "type": "tool_use",
                    "id": call["id"],
                    "name": call["name"],
                    "input": call["input"],
                })

            self.messages.append({"role": "assistant", "content": assistant_content})
            self.session_logger.log_assistant(text)

            if not tool_uses:
                if text:
                    print()
                return text

            tool_results = self._run_tool_batches(tool_uses)

            # Track consecutive errors for auto-retry logic
            has_errors = any("[ERROR]" in str(r.get("content", "")) for r in tool_results)
            if has_errors:
                consecutive_errors += 1
                if consecutive_errors >= MAX_TOOL_RETRIES:
                    # Inject a hint to the model to try a different approach
                    hint = {
                        "type": "tool_result",
                        "tool_use_id": tool_results[-1]["tool_use_id"],
                        "content": tool_results[-1]["content"] + "\n\n[CIPHER HINT: This has failed multiple times. Try a different approach — check paths, permissions, or syntax.]",
                    }
                    tool_results[-1] = hint
                    print(f"\033[93m  ⚠ Multiple failures — nudging toward a different approach\033[0m")
            else:
                consecutive_errors = 0

            self.messages.append({"role": "user", "content": tool_results})
            print()
