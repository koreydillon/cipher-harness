# Agensi listing: safe-command-guardrails

(Not part of the upload. Copy fields into the Agensi form.)

## Listing title

Safe Command Guardrails for Coding Agents

## Tagline

Block, confirm, or allow every shell, git, SQL, and cloud command before your agent runs it, and catch credential leaks on the way.

## Full description

Coding agents run commands constantly, and most of the time that is fine. The problem is the one command in a thousand that force-pushes over a teammate's work, truncates a table, or echoes an API key into a shared transcript. This skill gives your agent a clear, four-tier rule for deciding what to run.

BLOCK covers damage no project can justify: deleting root or home, formatting disks, fork bombs. SECRET covers anything that would print, stage, or upload a credential. CONFIRM covers recursive deletes, pushes, history rewrites, destructive SQL, infrastructure teardown, and package publishing. Everything else is ALLOW. The agent refuses the first two, asks before the third, and runs the fourth.

The SKILL.md is advisory. It teaches the agent how to decide and when autonomous mode does and does not count as consent. For a hard stop that does not depend on the model's judgment, the package includes a standard-library Python script that applies the same tiers mechanically and returns a distinct exit code per tier. A reference page shows how to wire it as a Claude Code PreToolUse hook in a few lines of settings.json, and how other agents can call it from their own pre-exec hooks.

Every pattern lives in a readable reference file so you can tune the lists for your project. The script ships with a self-test you can run after any change. Patterns are conservative on purpose: a grep for a dangerous string is allowed, while the same string inside bash -c is blocked.

## Category

security

## Tags

agent-safety, shell, git, sql, secrets, hooks, claude-code, guardrails

## Compatible agents

Claude Code (with optional hook enforcement), Cursor, GitHub Copilot, Codex CLI, Gemini CLI, and any agent that reads SKILL.md files or can call a script before executing commands.

## Price

Free

## Example prompts

1. "Clean up the build directories and push this branch." The agent names both confirm-tier actions once and waits for a yes.
2. "Reset the dev database and reseed it." The agent checks for production signals first, then presents the DROP as a confirm step.
3. "Turn on autonomous mode and fix the failing tests." The agent stages changed files by name, never runs git add -A, and does not push because push was not requested.
