# Cipher

A terminal coding agent in the spirit of Claude Code — minimal, hackable, and built to be read end-to-end in an afternoon. ~3K lines of Python. Twelve tools. A plugin system. Run it against the Anthropic API, or point it at a local model via Ollama.

```
   ██████╗██╗██████╗ ██╗  ██╗███████╗██████╗
  ██╔════╝██║██╔══██╗██║  ██║██╔════╝██╔══██╗
  ██║     ██║██████╔╝███████║█████╗  ██████╔╝
  ██║     ██║██╔═══╝ ██╔══██║██╔══╝  ██╔══██╗
  ╚██████╗██║██║     ██║  ██║███████╗██║  ██║
   ╚═════╝╚═╝╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
```

## Why

Most agent frameworks are either toy demos or 50K-line cathedrals. Cipher is the in-between: every file fits on a screen, every tool is one Python module, and the agent loop is something you can actually fork and modify.

## Install

```bash
git clone https://github.com/koreydillon/cipher-harness.git cipher
cd cipher
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your ANTHROPIC_API_KEY
python3 main.py
```

## Features

- **12 built-in tools:** `bash`, `read`, `write`, `edit`, `glob`, `grep`, `web_fetch`, `search`, `codebase`, `task`, `agent` (sub-agents), `self_extend` (the agent can write its own tools at runtime).
- **Local model support.** Set `LOCAL_MODEL=true` and point `OLLAMA_URL` at any Ollama server running an OpenAI-compatible chat endpoint.
- **Cost tracking + hard budgets.** `/budget 1.00` and the agent refuses further calls once spent.
- **Auto-compaction.** Conversation summarizes itself before hitting the context window.
- **Undo.** `/undo` rolls back the last file change.
- **Branching.** `/branch` forks the current conversation so you can try an alternate approach without losing the original.
- **Session logs.** Every session is written to `.cipher/sessions/` as markdown — searchable, replayable, shareable.
- **Plugin system.** Drop a Python file with a `Tool` subclass into `~/.cipher/plugins/` and the agent picks it up next launch.
- **Project memory.** A `.cipher/memory.md` persists across sessions per project.
- **Autonomous mode.** `/auto` toggles consent-free execution (for CI, scripted runs, fearless evenings).

## Slash commands

```
/auto      toggle autonomous mode
/model     show/switch model (sonnet | haiku | opus | <full id>)
/init      scan and summarize the current project
/cost      session token + dollar breakdown
/memory    view/append project memory
/undo      revert last file change
/branch    fork the conversation
/export    write session log to a path
/tasks     show task list
/plugins   list loaded tools
/budget N  set a spend ceiling
/tools     list available tools
/reset     clear conversation history
/help      show commands
/exit      quit
```

## Architecture

```
main.py            REPL: input loop, slash commands, banner
agent.py           Agent loop: tool dispatch, retries, compaction triggers
tool.py            Tool base class + ToolResult dataclass
tools/             12 built-in tool implementations (one file each)
config.py          .env loader + typed config object
local_client.py    Ollama / OpenAI-compatible client adapter
compact.py         Conversation summarization when context fills up
cost_tracker.py    Token + dollar accounting
session.py         Markdown session logger
memory.py          Per-project memory.md read/append
plugins.py         Discovers and loads ~/.cipher/plugins/*.py
project_scanner.py Lightweight repo summary for /init
undo.py            File-change undo stack
```

## Writing a plugin

Drop this in `~/.cipher/plugins/weather.py`:

```python
from tool import Tool, ToolResult
import requests

class WeatherTool(Tool):
    name = "weather"
    description = "Get current weather for a city."
    is_read_only = True
    is_concurrency_safe = True
    input_schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }

    def call(self, args):
        city = args["city"]
        r = requests.get(f"https://wttr.in/{city}?format=3", timeout=10)
        return ToolResult(output=r.text)
```

Restart Cipher and `/tools` will list `weather` alongside the built-ins.

## Configuration

All settings live in `.env` (see `.env.example`). The most useful knobs:

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required unless `LOCAL_MODEL=true` |
| `CIPHER_DEFAULT_MODEL` | `claude-sonnet-4-6` | Aliases `sonnet`/`haiku`/`opus` accepted |
| `LOCAL_MODEL` | `false` | Use a local Ollama model instead |
| `OLLAMA_URL` | `http://localhost:11434/v1` | OpenAI-compatible base URL |
| `CIPHER_BUDGET` | unset | Hard spend ceiling in USD |
| `CIPHER_COMPACT_THRESHOLD` | `0.85` | Fraction of context window before auto-compact |
| `CIPHER_AUTO_MODE` | `false` | Start sessions in autonomous mode |
| `CIPHER_PLUGIN_DIR` | `~/.cipher/plugins` | Where to look for plugins |

## Status

This is the open-source harness — agent loop, tool system, REPL. A separate fine-tuning track (training data, LoRA weights, eval harness) lives privately and is not part of this repo.

Contributions welcome. Tools should be one file. Slash commands should be obvious. If a feature needs a paragraph to explain, it probably needs to be smaller.

## License

MIT — see [LICENSE](LICENSE).
