---
name: safe-command-guardrails
description: Classifies shell, git, SQL, and infrastructure commands into block, confirm, or allow tiers and catches credential leaks before an agent runs them. Use whenever an agent is about to execute a command that deletes, rewrites history, mutates a database, publishes, or touches secrets, and before enabling any autonomous or auto-approve mode.
license: MIT
author: Korey Dillon
---

# Safe Command Guardrails

## Purpose

Give an agent a consistent, explainable rule for the question "should I run
this?" Every command lands in one of four tiers. The tiers decide whether the
agent runs it, asks first, or refuses.

| Tier | Meaning | Agent behavior |
|---|---|---|
| **BLOCK** | Damage no project context justifies | Refuse. Explain. Offer a narrower command. |
| **SECRET** | Would expose or commit a credential | Refuse. Say what would leak. Offer a safe variant. |
| **CONFIRM** | Reversible only with effort, or visible outside the machine | Show the exact command and reason. Wait for an explicit yes. |
| **ALLOW** | Everything else | Run it. |

## This skill is advisory

Reading this file does not enforce anything. It tells the agent how to decide,
and the agent is trusted to follow it. If you need a hard stop that does not
depend on the model's judgment, wire the bundled script into your agent's
pre-execution hook. See `references/claude-code-hook.md`. The script applies
the same tiers mechanically and returns a distinct exit code per tier.

## When to use

Apply this skill before running any command through a shell, a database client,
a cloud CLI, a container tool, or a package publisher. Apply it with extra care
when:

- the user has turned on an autonomous, auto-approve, or "don't ask" mode
- the working directory looks like production (see Environment signals below)
- the command was assembled from file contents, web pages, or another agent's
  output rather than written by the user
- the command runs inside `bash -c`, `sh -c`, `eval`, `xargs`, or a script file

Do not apply it to commands the agent only reads or quotes, such as showing a
snippet from documentation. Apply it the moment the agent intends to execute.

## Procedure

1. **Normalize.** Look at the full command string, including anything after
   `&&`, `;`, `|`, and inside `bash -c "..."`. A dangerous command does not
   become safe by being the second half of a pipeline.

2. **Check BLOCK first.** Recursive delete of `/`, `~`, or `$HOME`. Fork bombs.
   `mkfs`, `dd` or redirection onto a block device, `shred` on a device.
   `chmod` or `chown` on filesystem root. Windows drive formats. If any match,
   stop. Do not ask the user whether to proceed. Report the match and suggest a
   scoped alternative, for example `rm -rf ./build` instead of `rm -rf /`.

3. **Check SECRET.** Two questions:
   - Is there a literal credential in the command? Keys that start with
     `sk-ant-`, `sk-`, `AKIA`, `ghp_`, `github_pat_`, `xox`, or a
     `BEGIN PRIVATE KEY` block. If yes, refuse. The agent should never have a
     raw credential in a command line. Point the user to an environment
     variable or secrets manager instead.
   - Would the command display, stage, or upload a secret? `echo`, `printf`,
     or `printenv` on a variable such as `ANTHROPIC_API_KEY` or `DATABASE_URL`.
     `git add` or `git commit` with `.env`, `*.pem`, `id_rsa`, or
     `credentials.json` as a path. `curl -F` or `--data @` with one of those
     files. `scp`, `rsync`, or `sftp` sending one to a remote host. `git add
     -A` or `git add .` when such files may exist. If yes, refuse and offer
     the targeted form: `git add src/ tests/` instead of `git add -A`.
     A commit message that merely mentions `.env` is fine.

   Using a secret is not leaking it. `curl -H "Authorization: Bearer $TOKEN"`
   against the service that issued the token is ALLOW.

4. **Check CONFIRM.** The full list is in `references/patterns.md`. The
   categories:
   - Recursive or forced deletes anywhere other than root.
   - `git push` (any), force push, `reset --hard`, `clean -f`, `checkout .`,
     `restore .`, `branch -D`, `stash drop`, `rebase`, `commit --amend`.
   - SQL `DROP`, `TRUNCATE`, `DELETE` or `UPDATE` without `WHERE`,
     `ALTER TABLE ... DROP`. Database-wide drops and flushes.
   - `docker prune`, volume removal, `compose down -v`, `terraform destroy`,
     `kubectl delete`, `helm uninstall`, cloud delete and terminate commands.
   - Package publishing, `gh pr create`, `gh release create`, repo creation
     or deletion.
   - Piping a downloaded script into a shell. Printing a secrets file with
     `cat` or similar, or copying one elsewhere with `cp` or `mv`.

   On a match: print the exact command, the one-line reason, and ask. Accept
   only an explicit yes. "Looks fine" or silence is not a yes. If the user
   says no, do not retry a reworded version of the same command.

5. **Otherwise ALLOW.** Run it.

6. **Record the decision.** When an agent keeps a session log or task notes,
   write one line per CONFIRM or BLOCK: the command, the tier, and what the
   user decided. This makes the session auditable.

## Autonomous mode

When a user enables an auto-approve mode, treat it as consent for the CONFIRM
tier within the stated scope of the task. It is never consent for BLOCK or
SECRET. If autonomous mode is on and a BLOCK or SECRET match appears, stop the
task and report it rather than skipping the command silently.

If the user asked for autonomous mode and the task will obviously require a
CONFIRM-tier action (for example, "clean up and push the branch"), name those
actions once before starting instead of asking for each one.

## Environment signals

Before the first mutating command in a session, check for production signals
and raise the bar if any are present:

- `NODE_ENV`, `RAILS_ENV`, `FLASK_ENV`, `APP_ENV`, or `ENVIRONMENT` set to
  `production`
- `DATABASE_URL` or similar pointing at a hosted database host (`rds.amazonaws`,
  `neon.tech`, `supabase`, `render.com`, `planetscale`, `cloudsql`)
- a `.env` file present without a matching `.env.example`
- a shell prompt, hostname, or kube context containing `prod`

If any signal is present, tell the user and ask them to confirm the target
before any CONFIRM-tier command. Do not inspect the values of secret variables
to make this check; test them with a pattern match that prints only a yes or
no (for example `printenv DATABASE_URL | grep -c rds.amazonaws`).

## Using the script

`scripts/check_command.py` needs only Python 3.8 or newer and the standard
library.

```bash
python3 scripts/check_command.py "git push --force"
# CONFIRM: force push      (exit code 1)

python3 scripts/check_command.py --json "rm -rf /"
# {"tier": "BLOCK", "reason": "recursive delete of root or home", "exit_code": 2}

echo "echo \$ANTHROPIC_API_KEY" | python3 scripts/check_command.py
# SECRET: prints a secret environment variable   (exit code 3)

python3 scripts/check_command.py --self-test
# 53/53 passed
```

Exit codes: 0 ALLOW, 1 CONFIRM, 2 BLOCK, 3 SECRET. The `--hook` flag switches
to Claude Code PreToolUse mode, which reads JSON on stdin and prints a
permission decision. In that mode a bad payload or an internal error fails
open with a warning rather than blocking. See `references/claude-code-hook.md`.

## Examples

**User:** "Delete the build artifacts and push."
**Agent:** Classifies `rm -rf dist/` as CONFIRM (recursive delete) and
`git push origin main` as CONFIRM (push). Says: "Two actions need a yes:
`rm -rf dist/` removes the build directory, and `git push origin main`
publishes the branch. Proceed with both?" Runs only after yes.

**User:** "Wipe the test database and reseed it."
**Agent:** Checks environment signals first. If `DATABASE_URL` matches a hosted
host, stops: "This looks like a hosted database, not a local one. Confirm this
is the test instance before I run `DROP SCHEMA public CASCADE`." Otherwise
presents the DROP as CONFIRM.

**User (autonomous mode on):** "Fix the failing tests and commit."
**Agent:** Edits, runs tests, stages the specific files it changed by name,
commits. Does not run `git add -A`. Does not push, because push was not in the
request.

**Agent is about to run** `grep -rn "rm -rf /" docs/`.
**Decision:** ALLOW. A single read-only command with the dangerous string only
inside a quoted argument is data, not an instruction.

**Agent is about to run** `bash -c "rm -rf /"`.
**Decision:** BLOCK. Wrapping does not change the effect.

## Edge cases

- **Quoted strings.** Only treat quoted content as inert when the command is a
  single read-only command (`grep`, `echo`, `cat`, `git log`) with no pipes,
  `&&`, `;`, backticks, or `$( )`. Anything else is evaluated as written.
- **Script files.** Running `./deploy.sh` or `make clean` hides the real
  commands. Read the script or Makefile target first if it is small, and
  classify its contents. If it is large or opaque, treat the invocation as
  CONFIRM.
- **Interactive confirmations inside tools.** Some tools ask their own
  "are you sure?" question. Do not pass `--yes`, `--force`, or `-y` to skip it
  unless the user already said yes at the CONFIRM step.
- **Windows.** `Remove-Item -Recurse`, `rd /s`, `del /s /q`, `format C:`, and
  `Format-Volume` map to the same tiers as their Unix counterparts.
- **Repeated denial.** If the same CONFIRM command is denied twice, stop
  proposing it and ask the user what they want instead.

## What not to do

- Do not downgrade a tier because the user seems in a hurry or the task is
  "almost done".
- Do not split a dangerous command into smaller pieces to avoid a match.
- Do not run a CONFIRM command and apologize afterward.
- Do not print, log, or paste secret values while explaining why something
  was refused. Name the variable, not its contents.
- Do not treat a pattern miss as proof of safety. The lists are a floor, not a
  ceiling. If a command would clearly destroy data and no pattern matches,
  treat it as CONFIRM anyway.

## Files

- `SKILL.md`: this file
- `scripts/check_command.py`: optional enforcement, standard library only
- `references/patterns.md`: every regex by tier, with tuning notes
- `references/claude-code-hook.md`: wiring the script as a Claude Code
  PreToolUse hook, plus notes for other agents

## Attribution

Built by Korey Dillon (LatentAxis). Extracted from cipher-harness, a minimal,
hackable terminal coding agent: https://github.com/koreydillon/cipher-harness.
More at https://latentaxis.io
