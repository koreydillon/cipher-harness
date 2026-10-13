# Agensi listing: codebase-orientation

(Not part of the upload. Copy fields into the Agensi form.)

## Listing title

Codebase Orientation: Map a Repo in 10 Tool Calls

## Tagline

A cheap, deterministic procedure that gets your agent oriented in an unfamiliar repository before it spends tokens reading files or risks editing production.

## Full description

Dropping an agent into a repository it has never seen usually goes one of two ways. It reads dozens of files and burns context before doing any work, or it guesses at a file and edits the wrong thing. This skill replaces both with a short, repeatable procedure built on file listing, search, and a handful of reads.

The agent identifies the project type and stack from manifest files, captures git state, maps the tree by directory with entry points, config, tests, and the largest files, then traces imports and importers for the files the task actually touches. When the task names a concept rather than a file, a concept-to-regex reference maps "auth", "webhooks", "retries", and two dozen other ideas to search patterns that work across languages. Files are ranked by hit count and only the top few get read.

Before any change, the agent checks for production signals: framework environment variables, hosted database hosts, a stray .env file, a kube context with prod in the name. If one fires, the agent stops and asks you to confirm the target instead of assuming. It never prints the secret values it is checking.

The whole thing targets 8 to 15 tool calls and at most three full file reads. Example commands are given for both Unix shells and PowerShell. The output is a 40-line summary your agent can store in project memory so the next session skips the scan.

## Category

productivity

## Tags

codebase, onboarding, repository, search, grep, orientation, agent-workflow, context-efficiency

## Compatible agents

Claude Code, Cursor, GitHub Copilot, Codex CLI, Gemini CLI, and any agent that reads SKILL.md files and can list, search, and read files.

## Price

Free

## Example prompts

1. "What is this repo and how do I run it?" The agent returns the type, stack, run and test commands, layout, and entry points without reading more than the entry file.
2. "Where do we handle payment webhooks?" The agent searches the webhook and api concept patterns plus the word payment, ranks files by hits, and reports the top three with their imports and importers.
3. "Add a retry to the fetch in the sync job." The agent finds the job file, notices an existing retry helper in a module it imports, checks for production signals, and reports both before editing.
