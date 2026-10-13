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

If the payload is not a Bash call, or has no command, the hook stays silent
with exit 0, which means "no decision" and your normal permission flow runs.

Two things worth knowing about `ask` and `deny`:

- A hook `ask` forces the permission prompt even in auto mode. The prompt shows
  the reason text. So CONFIRM-tier commands still get a human decision when
  the user has otherwise told Claude Code not to ask.
- A hook `deny` prevents the call and the reason is shown to Claude, so it can
  explain the refusal and propose a safer command.
- Permission rules in your settings are still evaluated on top of whatever the
  hook returns. The hook can add an objection, never remove one.

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

## Failure behavior

The hook is designed to fail open. A broken hook must never turn into a lockout
where every Bash call is blocked, and it must never fail silently either. The
rule: a decision is only ever made on a well-formed payload with a successful
classification. Anything else produces exit 1 and a one-line warning on
stderr. Claude Code treats exit 1 as a non-blocking hook error, shows the
notice `PreToolUse:Bash hook error` with the first line of stderr in the
transcript, and lets the call continue through the normal permission flow.

| Case | Script behavior | What Claude Code does |
|---|---|---|
| Malformed JSON on stdin | exit 1, stderr `safe-command-guardrails hook: malformed JSON on stdin (...); failing open` | Non-blocking error notice. Call proceeds under normal permissions. |
| Empty stdin | exit 1, stderr `... empty stdin, expected PreToolUse JSON; failing open` | Same. |
| Non-Bash tool, or no `command` field | exit 0, no output | No decision. Call proceeds under normal permissions. Not an error, so no notice. |
| Script crashes (classifier bug, import failure, stdin read error) | exit 1, stderr `... classifier error <Type>: <message>; failing open` | Non-blocking error notice. Call proceeds under normal permissions. |
| Interpreter not found on PATH | The shell exits 127 before the script runs, stderr `python3: command not found` | Non-blocking error notice with that shell message. Call proceeds under normal permissions. Every Bash call will show the notice until the path is fixed. |

All five cases are exercised by `--self-test` except the missing interpreter,
which is a property of the shell, not the script.

If you want the opposite policy, where a failing hook blocks the call, add
`"onFailure": "block"` to the hook entry (Claude Code v2.1.295 or later). With
that setting, every row above except the non-Bash row becomes a block,
including the missing-interpreter case. Only do this if you are confident the
interpreter path is stable, otherwise a PATH change locks out every shell
command.

### Pointing the hook at a specific interpreter

The default snippet uses `python3`, which is right for macOS and most Linux
distributions. If the notice says `command not found`, pin the interpreter:

| Platform | Use |
|---|---|
| macOS, Linux with `python3` on PATH | `python3 ~/.claude/skills/safe-command-guardrails/scripts/check_command.py --hook` |
| Linux where only `python` exists | `python ~/.claude/skills/safe-command-guardrails/scripts/check_command.py --hook` |
| Any system, most robust | an absolute path, for example `/usr/bin/python3 ...` or `/opt/homebrew/bin/python3 ...` |
| Windows with the Python launcher | `py -3 %USERPROFILE%\.claude\skills\safe-command-guardrails\scripts\check_command.py --hook` |
| Windows without the launcher | `python %USERPROFILE%\.claude\skills\safe-command-guardrails\scripts\check_command.py --hook` |

Find the absolute path with `which python3` (Unix) or `where python` and
`py -0p` (Windows). You can also use the exec form with `"command"` set to the
interpreter and `"args"` holding the script path and `--hook`, which avoids
quoting problems with spaces in paths.

### Reproducing the tests by hand

```bash
S=~/.claude/skills/safe-command-guardrails/scripts/check_command.py
printf '{"tool_name":"Bash","tool_input":{' | python3 $S --hook; echo "exit=$?"
printf '' | python3 $S --hook; echo "exit=$?"
printf '{"tool_name":"Read","tool_input":{"file_path":"/etc/hosts"}}' | python3 $S --hook; echo "exit=$?"
```

Expected: the first two print a warning to stderr and exit 1, the third prints
nothing and exits 0.

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
