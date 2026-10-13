# Enforcing the guardrails with a hook

`SKILL.md` on its own is advisory. The agent reads it and is expected to follow
it, but nothing stops a command from running. This page shows how to make the
tiers binding by running `scripts/check_command.py` before every shell call.

## Claude Code: PreToolUse hook on Bash

Claude Code runs hooks declared in `settings.json`. A `PreToolUse` hook with a
`Bash` matcher receives the pending command as JSON on stdin and can return a
permission decision as JSON on stdout.

1. Install the skill so the script has a stable path. The examples assume
   `~/.claude/skills/safe-command-guardrails/`.

2. Add this to `~/.claude/settings.json` for every project, or to
   `.claude/settings.json` inside one repository:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/skills/safe-command-guardrails/scripts/check_command.py --hook"
          }
        ]
      }
    ]
  }
}
```

On Windows, replace `python3` with `python` or `py -3` and use a full path
such as `%USERPROFILE%\.claude\skills\safe-command-guardrails\scripts\check_command.py`.

3. Restart Claude Code or start a new session. Hooks are read at startup.

### What the hook does

In `--hook` mode the script reads the hook payload, pulls `tool_input.command`,
classifies it, and prints one of these decisions:

| Tier | `permissionDecision` | Effect in Claude Code |
|---|---|---|
| BLOCK | `deny` | The command never runs. Claude sees the reason. |
| SECRET | `deny` | Same as BLOCK, with the leak reason. |
| CONFIRM | `ask` | The normal permission prompt appears with the reason attached, even in auto-approve modes. |
| ALLOW | no output | The hook stays silent and your usual permission settings apply. |

The script always exits 0 in hook mode so that a parsing problem never
turns into a confusing "hook error" banner. If the payload is not a Bash call,
or has no command, the hook stays silent.

### Checking it works

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force"}}' \
  | python3 ~/.claude/skills/safe-command-guardrails/scripts/check_command.py --hook
```

Expected output:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "safe-command-guardrails CONFIRM: force push"}}
```

Then inside a Claude Code session, ask the agent to run `rm -rf /`. It should
be denied before it executes, and the agent should explain why.

## Other agents

Any agent runtime with a pre-execution hook, wrapper, or policy callback can
call the same script. Use the plain CLI mode and branch on the exit code:

```bash
python3 check_command.py "$COMMAND"
case $? in
  0) run_it ;;
  1) ask_user_then_maybe_run ;;
  2|3) refuse_and_show_reason ;;
esac
```

Or ask for JSON:

```bash
python3 check_command.py --json "$COMMAND"
# {"tier": "CONFIRM", "reason": "force push", "exit_code": 1}
```

Known integration points as of this writing:

- **Cursor**: hooks configuration supports pre-command checks for shell
  execution. Point the command at the script in CLI mode and treat exit codes
  1, 2, and 3 as deny or ask depending on what the hook API allows.
- **Codex CLI**, **Copilot CLI**, **Gemini CLI**, and other tools: check the
  current documentation for a pre-tool or pre-exec hook. If none exists, run the
  agent inside a wrapper shell function that calls the script before `exec`.
- **Custom harnesses**: import the module and call `classify(cmd)` directly.
  It returns `(tier, reason)` and has no dependencies.

Agent hook APIs change often. If a snippet above no longer matches your tool,
the script's contract stays the same: command in, tier and reason out, exit
code 0, 1, 2, or 3.
