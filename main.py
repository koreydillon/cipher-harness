#!/usr/bin/env python3
"""
Cipher — Coding Agent
Usage: python3 main.py [--no-banner]
"""
import os
import sys
import argparse

import config as _config
_config.load()   # populate os.environ from .env before any other import reads it
from config import cfg  # noqa: E402

BANNER = """
\033[38;5;39m   ██████╗██╗██████╗ ██╗  ██╗███████╗██████╗ \033[0m
\033[38;5;33m  ██╔════╝██║██╔══██╗██║  ██║██╔════╝██╔══██╗\033[0m
\033[38;5;27m  ██║     ██║██████╔╝███████║█████╗  ██████╔╝\033[0m
\033[38;5;21m  ██║     ██║██╔═══╝ ██╔══██║██╔══╝  ██╔══██╗\033[0m
\033[38;5;57m  ╚██████╗██║██║     ██║  ██║███████╗██║  ██║\033[0m
\033[38;5;93m   ╚═════╝╚═╝╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝\033[0m
\033[90m  coding agent — v0.3.0\033[0m
"""

HELP = """\033[90mCommands:
  /auto              — toggle autonomous mode (no confirmation needed)
  /model [name]      — show or switch model
  /init              — scan & summarize current project
  /cost              — show session cost breakdown
  /memory            — view/append project memory
  /undo              — undo last file change
  /branch            — branch conversation for alternative approach
  /export [path]     — export session log
  /tasks             — show task list
  /plugins           — list loaded plugins
  /budget N          — set max spend in dollars
  /clear             — clear screen
  /reset             — clear conversation history
  /tools             — list available tools
  /help              — show this message
  /exit              — quit\033[0m
"""


def check_api_key():
    if cfg.local_model:
        return None   # local model — no key needed
    key = cfg.anthropic_api_key
    if not key:
        print("\033[91m[cipher] ANTHROPIC_API_KEY not set.\033[0m")
        print("  Option 1 — set it in your shell:  export ANTHROPIC_API_KEY=sk-ant-...")
        print("  Option 2 — add it to .env:        ANTHROPIC_API_KEY=sk-ant-...")
        print("  Option 3 — use a local model:     LOCAL_MODEL=true  (see .env.example)")
        sys.exit(1)
    return key


def prompt_line(agent) -> str:
    cost_str = agent.cost_tracker.format_status()
    ctx_pct = agent.cost_tracker.context_pct(agent.messages, agent.model)
    ctx_str = f"{int(ctx_pct * 100)}%"
    # Short model name
    model_short = agent.model.split("/")[-1].split(":")[0]
    # Short cwd
    cwd_short = os.path.basename(agent.cwd) or agent.cwd
    auto_tag = " \033[93mAUTO\033[38;5;39m |" if agent.autonomous_mode else ""
    return f"\033[38;5;39m╭─ {cwd_short} [{model_short}]\n╰▶\033[0m\033[38;5;39m [{cost_str} | ctx:{ctx_str}{auto_tag}] \033[0m"


def handle_cost(agent):
    try:
        from rich.table import Table
        from rich.console import Console
        console = Console()
        t = Table(title="Session Cost", show_header=True)
        t.add_column("Field", style="cyan")
        t.add_column("Value", style="white")
        t.add_row("Model", agent.model)
        t.add_row("Input tokens", f"{agent.cost_tracker.input_tokens:,}")
        t.add_row("Output tokens", f"{agent.cost_tracker.output_tokens:,}")
        t.add_row("Total tokens", f"{agent.cost_tracker.input_tokens + agent.cost_tracker.output_tokens:,}")
        t.add_row("Session cost", f"${agent.cost_tracker.session_cost():.4f}")
        if agent.budget:
            pct = agent.cost_tracker.session_cost() / agent.budget * 100
            t.add_row("Budget", f"${agent.budget:.2f} ({pct:.1f}% used)")
        console.print(t)
    except ImportError:
        print(f"  Model:   {agent.model}")
        print(f"  Input:   {agent.cost_tracker.input_tokens:,} tokens")
        print(f"  Output:  {agent.cost_tracker.output_tokens:,} tokens")
        print(f"  Cost:    ${agent.cost_tracker.session_cost():.4f}")


def handle_tasks(agent):
    try:
        from rich.table import Table
        from rich.console import Console
        import json
        tasks_path = os.path.join(agent.cwd, ".cipher", "tasks.json")
        if not os.path.exists(tasks_path):
            print("\033[90m  No tasks.\033[0m")
            return
        with open(tasks_path) as f:
            tasks = json.load(f)
        if not tasks:
            print("\033[90m  No tasks.\033[0m")
            return
        console = Console()
        t = Table(title="Tasks", show_header=True)
        t.add_column("ID", style="dim", width=4)
        t.add_column("Status", width=12)
        t.add_column("Description")
        icons = {"pending": "⬜ pending", "in_progress": "🔄 in_progress", "done": "✅ done"}
        for task in tasks:
            t.add_row(str(task["id"]), icons.get(task["status"], task["status"]), task["description"])
        console.print(t)
    except ImportError:
        task_tool = agent.tool_map.get("task")
        if task_tool:
            result = task_tool.call({"action": "list"})
            print(result.output)


def handle_plugins(agent):
    try:
        from rich.table import Table
        from rich.console import Console
        console = Console()
        t = Table(title="Loaded Tools", show_header=True)
        t.add_column("Name", style="cyan")
        t.add_column("Mode", style="dim")
        t.add_column("Description")
        for tool in agent.tools:
            mode = "read-only" if tool.is_read_only else "read-write"
            if tool.is_concurrency_safe:
                mode += " | concurrent"
            t.add_row(tool.name, mode, tool.description[:70])
        console.print(t)
    except ImportError:
        for tool in agent.tools:
            mode = "read-only" if tool.is_read_only else "read-write"
            print(f"  \033[38;5;39m{tool.name}\033[0m  [{mode}]  {tool.description[:60]}")


def handle_memory(agent):
    from memory import load_memory, append_memory
    try:
        from rich.panel import Panel
        from rich.console import Console
        console = Console()
        content = load_memory(agent.cwd)
        if content:
            console.print(Panel(content, title="Project Memory", border_style="blue"))
        else:
            print("\033[90m  No project memory yet.\033[0m")
    except ImportError:
        content = load_memory(agent.cwd)
        print(content if content else "\033[90m  No project memory yet.\033[0m")

    try:
        ans = input("\033[90mAppend to memory? (y/n): \033[0m").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return
    if ans == "y":
        try:
            entry = input("\033[90mEntry: \033[0m").strip()
            if entry:
                append_memory(agent.cwd, entry)
                print("\033[90m  Memory updated.\033[0m")
        except (KeyboardInterrupt, EOFError):
            print()


def main():
    parser = argparse.ArgumentParser(description="Cipher coding agent")
    parser.add_argument("--no-banner", action="store_true")
    args = parser.parse_args()

    api_key = check_api_key()

    from agent import CipherAgent
    agent = CipherAgent(api_key=api_key)

    # Apply budget from config if not already set at runtime
    if agent.budget is None and cfg.budget is not None:
        agent.budget = cfg.budget

    # Apply autonomous mode from config
    if cfg.auto_mode:
        agent.autonomous_mode = True

    if not args.no_banner:
        print(BANNER)
        print(HELP)

    print(f"\033[90mWorking directory: {agent.cwd}\033[0m")
    print(f"\033[90mSession log: {agent.session_logger.path}\033[0m\n")

    while True:
        try:
            user_input = input(prompt_line(agent)).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\033[90m[cipher] bye.\033[0m")
            break

        if not user_input:
            continue

        # ── Commands ──────────────────────────────────────────────────────────

        if user_input == "/exit":
            print("\033[90m[cipher] bye.\033[0m")
            break

        elif user_input == "/reset":
            agent.reset()
            print("\033[90m[cipher] conversation reset.\033[0m\n")

        elif user_input == "/clear":
            os.system("clear")

        elif user_input == "/auto":
            agent.autonomous_mode = not agent.autonomous_mode
            agent._bash_tool.autonomous_mode = agent.autonomous_mode
            agent._write_tool.autonomous_mode = agent.autonomous_mode
            state = "ON" if agent.autonomous_mode else "OFF"
            if agent.autonomous_mode:
                print(f"\033[93m[cipher] autonomous mode {state} — agent will act without confirmation.\033[0m\n")
            else:
                print(f"\033[90m[cipher] autonomous mode {state}.\033[0m\n")

        elif user_input.startswith("/model"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 1:
                print(f"\033[90m  Current model: {agent.model}\033[0m\n")
            else:
                agent.switch_model(parts[1].strip())
                print()

        elif user_input == "/init":
            print("\033[38;5;39m  Scanning project...\033[0m")
            from project_scanner import scan_project
            ctx = scan_project(agent.cwd)
            print(f"\033[90m{ctx}\033[0m")
            # Feed it to the agent so it knows the project
            agent.run("Scan this project directory. List the key files, what the project does, the tech stack, and any issues you spot. Be brief.")
            print()

        elif user_input == "/cost":
            handle_cost(agent)
            print()

        elif user_input == "/memory":
            handle_memory(agent)
            print()

        elif user_input == "/undo":
            msg = agent.undo_stack.undo_last()
            print(f"\033[90m[cipher] {msg}\033[0m\n")

        elif user_input == "/branch":
            branched = agent.branch()
            print("\033[90m[cipher] Branch created. Type your alternative approach.\033[0m")
            print("\033[90m(This is a new branch — original conversation preserved)\033[0m\n")
            # Replace agent with branch for this session
            agent = branched

        elif user_input.startswith("/export"):
            parts = user_input.split(maxsplit=1)
            dest = parts[1].strip() if len(parts) > 1 else "./cipher-session.md"
            try:
                out = agent.session_logger.export(dest)
                print(f"\033[90m[cipher] exported to {out}\033[0m\n")
            except Exception as e:
                print(f"\033[91m[cipher] export failed: {e}\033[0m\n")

        elif user_input == "/tasks":
            handle_tasks(agent)
            print()

        elif user_input == "/plugins":
            handle_plugins(agent)
            print()

        elif user_input.startswith("/budget"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 1:
                if agent.budget:
                    print(f"\033[90m  Budget: ${agent.budget:.2f}\033[0m\n")
                else:
                    print("\033[90m  No budget set.\033[0m\n")
            else:
                try:
                    agent.budget = float(parts[1].strip())
                    print(f"\033[90m[cipher] budget set to ${agent.budget:.2f}\033[0m\n")
                except ValueError:
                    print("\033[91m[cipher] invalid budget value.\033[0m\n")

        elif user_input == "/tools":
            for t in agent.tools:
                rw = "read-only" if t.is_read_only else "read-write"
                safe = " | concurrent" if t.is_concurrency_safe else ""
                print(f"  \033[38;5;39m{t.name}\033[0m  [{rw}{safe}]  — {t.description[:70]}")
            print()

        elif user_input == "/help":
            print(HELP)

        elif user_input.startswith("/"):
            print(f"\033[90m  Unknown command: {user_input}. Type /help for commands.\033[0m\n")

        else:
            print()
            try:
                agent.run(user_input)
            except KeyboardInterrupt:
                print("\n\033[90m[cipher] interrupted.\033[0m")
            except Exception as e:
                print(f"\n\033[91m[cipher] error: {e}\033[0m")
            print()


if __name__ == "__main__":
    main()
