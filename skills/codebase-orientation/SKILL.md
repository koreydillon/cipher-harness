---
name: codebase-orientation
description: Builds a fast, cheap map of an unfamiliar repository using only file listing, search, and a handful of reads, then checks for production environment signals before any change. Use at the start of work in a new or large codebase, when a user asks "what is this project" or "where does X live", or before the first edit in a repo the agent has not seen this session.
license: MIT
author: Korey Dillon
---

# Codebase Orientation

## Purpose

Get an agent from "I have never seen this repo" to "I know the stack, the entry
points, the file that matters for this task, and whether I am pointed at
production" in a few minutes and a small number of tool calls. Deterministic
heuristics first, model reasoning second. Reading every file is slow,
expensive, and usually unnecessary.

## When to use

- First task in a session inside a repository the agent has not mapped.
- The user asks what the project does, how it is organized, or where something
  lives.
- Before the first file edit in a repo, even for a small change, when the agent
  cannot yet name the file it needs to touch.
- When a task mentions a concept ("the auth flow", "where we talk to the
  database") rather than a file.

Skip it when the user names the exact file and the change is local to it.

## Inputs and outputs

**Inputs:** the working directory. Optionally, the task description, which
focuses steps 4 and 5.

**Output:** an orientation summary in the template at the end of this file,
under 40 lines, plus a decision about whether it is safe to mutate anything.
If the agent has a persistent memory or notes file for the project, store the
summary there so later sessions skip the scan.

## Budget

Aim for 8 to 15 tool calls total. Read at most three files end to end: the
entry point and up to two files the task points at. Everything else comes from
listings, line counts, and search hits. If the repo has more than roughly 2,000
code files, scope the scan to the subtree the task concerns and say so.

## Procedure

### Step 1: Identify the project type and stack

Look for manifest files at the root, then one level down for monorepos.

| File present | Type | Read for stack |
|---|---|---|
| `pyproject.toml`, `setup.py`, `requirements.txt` | Python | dependency list, first 5 entries |
| `package.json` | Node or browser | `dependencies`, `devDependencies`, `scripts` |
| `Cargo.toml` | Rust | `[dependencies]` |
| `go.mod` | Go | `require` block |
| `pom.xml`, `build.gradle` | JVM | dependency section |
| `Gemfile` | Ruby | gems |
| `*.csproj`, `*.sln` | .NET | package references |
| `Dockerfile`, `docker-compose.yml` | containerized | base image, services |
| `Makefile`, `justfile`, `Taskfile.yml` | task runner | target names |

Name the framework when a dependency makes it obvious (Django, FastAPI, Next.js,
Rails, Spring). Note the task runner targets or `package.json` scripts; they
tell you how the project is run and tested.

### Step 2: Capture git state

Branch, whether the tree is dirty, and the last five commit subjects. The
commit subjects say what people have been working on, which is often the best
hint about where the current task lands.

```
git rev-parse --abbrev-ref HEAD
git status --short
git log --oneline -5
```

Same commands in every shell. If git is absent, say so and continue.

### Step 3: Map the tree

List source files, skipping generated and vendored directories:
`node_modules`, `.git`, `__pycache__`, `.venv`, `venv`, `dist`, `build`,
`.next`, `target`, `vendor`, `coverage`, `.cache`, `.tox`, `.mypy_cache`,
`.pytest_cache`, `.idea`, `.vscode`.

Prefer `git ls-files` when the repo is tracked; it already respects
`.gitignore`. Otherwise:

Unix shell:

```bash
git ls-files | grep -vE '^(node_modules|dist|build|vendor)/' | head -300
# or, outside git:
find . -type f \( -name '*.py' -o -name '*.ts' -o -name '*.go' \) \
  -not -path '*/node_modules/*' -not -path '*/.git/*' | head -300
wc -l $(git ls-files '*.py') | sort -n | tail -15
```

PowerShell:

```powershell
git ls-files | Where-Object { $_ -notmatch '^(node_modules|dist|build|vendor)/' } | Select-Object -First 300
# or, outside git:
Get-ChildItem -Recurse -File -Include *.py,*.ts,*.go |
  Where-Object { $_.FullName -notmatch '\\(node_modules|\.git)\\' } | Select-Object -First 300
Get-ChildItem -Recurse -Include *.py | ForEach-Object { [pscustomobject]@{ Lines = (Get-Content $_ | Measure-Object -Line).Lines; File = $_.FullName } } | Sort-Object Lines | Select-Object -Last 15
```

From the listing, pull out:

- **Entry points:** `main.*`, `app.*`, `index.*`, `server.*`, `cli.*`,
  `manage.py`, `cmd/*/main.go`, `src/main.rs`, anything named in
  `package.json` `"main"` or `"bin"`, or in a Dockerfile `CMD`.
- **Config:** files with `config`, `settings`, `.env`, `setup` in the name.
- **Tests:** files or directories containing `test` or `spec`. Count them.
- **Largest files:** the top 10 to 15 by line count. These are where the
  complexity lives.

Group the result by top-level directory. One line per directory with its
purpose is enough.

### Step 4: Trace the files that matter for the task

Pick the entry point and the one or two files the task points at. For each,
find what it imports and what imports it.

Imports (what this file depends on):

| Language | Search in the file for |
|---|---|
| Python | lines starting with `import ` or `from ` |
| JS, TS | `import ... from '...'` and `require('...')` |
| Go | the `import (` block |
| Rust | `use crate::` and `mod ` |

Imported by (who depends on this file), searching the whole tree for the
module name:

```bash
grep -rln --include='*.py' -E '(from|import) +(\.|\w+\.)*payments\b' .
```

```powershell
Get-ChildItem -Recurse -Include *.py | Select-String -Pattern '(from|import) +(\.|\w+\.)*payments\b' -List | Select-Object -ExpandProperty Path
```

Also list files with a similar name (`payments.py`, `payments_test.py`,
`payment_service.ts`); they are usually related even without an import.

Read the entry point fully. Read the task files fully only if they are under a
few hundred lines; otherwise read the top 60 lines and the definitions that
search hits point at.

### Step 5: Search by concept

When the task names a concept rather than a file, use the concept-to-pattern
table in `references/search-map.md`. Each concept maps to a short list of
regular expressions that find it in most languages. Search for all patterns in
the group, rank files by hit count, and read the top two or three.

```bash
grep -rnE --include='*.py' --include='*.ts' 'try:|except |catch\s*\(|\.catch\(|raise |throw ' . | cut -d: -f1 | sort | uniq -c | sort -rn | head
```

```powershell
Get-ChildItem -Recurse -Include *.py,*.ts | Select-String -Pattern 'try:|except |catch\s*\(|\.catch\(|raise |throw ' | Group-Object Path | Sort-Object Count -Descending | Select-Object -First 10 Count,Name
```

If a concept is not in the map, build a pattern from two or three distinctive
words in the task description and the function or class names you already saw
in step 3.

### Step 6: Check environment signals before any mutation

This step is mandatory before the first command or edit that changes anything.
Check for production indicators without printing secret values:

| Signal | Unix shell | PowerShell |
|---|---|---|
| Framework env set to production | `printenv NODE_ENV RAILS_ENV FLASK_ENV APP_ENV ENVIRONMENT` | `$env:NODE_ENV; $env:RAILS_ENV; $env:APP_ENV; $env:ENVIRONMENT` |
| Hosted database URL | `printenv DATABASE_URL \| grep -cE 'rds\.amazonaws\|neon\.tech\|supabase\|render\.com\|planetscale\|cloudsql'` | `[bool]($env:DATABASE_URL -match 'rds\.amazonaws\|neon\.tech\|supabase\|render\.com\|planetscale\|cloudsql')` |
| Secrets present | `.env` exists and `.env.example` does not | same check with `Test-Path` |
| Kube or cloud context named prod | `kubectl config current-context 2>/dev/null \| grep -i prod` | `kubectl config current-context 2>$null \| Select-String prod` |

**If any signal is present, stop and confirm with the user before making any
change.** Say which signal fired and ask them to confirm the target is the one
they intend. Do not continue on an assumption. Do not read, echo, or paste the
value of `DATABASE_URL` or any key; the count or boolean is all you need.

If no signal is present, note "no production signals" in the summary and
continue.

### Step 7: Write the summary and persist it

Fill the template below. Keep it under 40 lines. If the agent has a project
memory, notes file, or similar persistent store, save it there with the date
so the next session can skip steps 1 through 3.

## Output template

```
## Orientation: <repo name>

Type and stack: <language>, <framework>, <notable deps>
Run and test:   <commands from scripts, Makefile, or README>
Git:            branch <name>, <clean|N changed files>, last commit "<subject>"

Layout:
  <dir>/   <purpose, 1 line>
  <dir>/   <purpose, 1 line>

Entry points:  <files>
Config:        <files>
Tests:         <count> files under <dir>
Largest files: <file> (<n> lines), <file> (<n> lines), <file> (<n> lines)

For this task:
  <file>  imports <a, b>; imported by <c, d>
  <file>  found via concept "<concept>", <n> hits

Environment:   no production signals | STOP: <signal> detected, awaiting confirmation

Open questions: <anything the scan could not settle>
```

## Examples

**User:** "Where do we handle payment webhooks?"
**Agent:** Steps 1 to 3 in five calls. Step 5 with the `api` and `webhook`
concepts plus the words `payment` and `stripe`. Ranks `api/webhooks.py` first
with 14 hits. Step 4 shows it imports `services.billing` and is imported by
`urls.py`. Summary names those three files and nothing else.

**User:** "Add a retry to the fetch in the sync job."
**Agent:** Step 3 listing shows `jobs/sync.py`. Step 4 finds it imports
`http_client.py`, which already has a retry helper. Reports that in the
summary so the user can decide whether to reuse it. Step 6 finds
`DATABASE_URL` matches a hosted host. Stops: "This shell points at a hosted
database. Confirm this is the environment you want me to edit in before I
change anything."

**User:** "What is this repo?"
**Agent:** Steps 1 to 3 and 7 only. Skips 4 and 5 because there is no task.
Returns the summary with the "For this task" block omitted.

## Edge cases

- **Monorepo.** Run step 1 at root and in each package directory that has a
  manifest. Report the packages as the layout and scope steps 3 to 5 to the
  package the task concerns.
- **No manifest.** Infer language from file extensions. Say that the stack is
  inferred.
- **Huge repo.** Over about 2,000 code files, scope to the task's subtree and
  state the scope in the summary. Do not list everything.
- **Generated code.** Directories such as `migrations/`, `generated/`,
  `__snapshots__/`, and `*.pb.go` inflate line counts. Exclude them from the
  largest-files list and mention them once.
- **Binary and data files.** Skip anything over about 100 KB or with a
  non-text extension.
- **No shell access.** Do steps 1 to 5 with the agent's native file listing,
  search, and read tools. Do step 6 by reading `.env` names (not values) and
  config files for an environment setting, and ask the user about the database
  target directly.

## What not to do

- Do not read every file. The point is to avoid that.
- Do not run `install`, `build`, or `test` as part of orientation. Those are
  mutations and belong to the task, after step 6.
- Do not modify anything, including creating a notes file inside the repo,
  until step 6 passes.
- Do not print secret values while checking for production signals.
- Do not pad the summary. If a section has nothing to say, drop it.

## Files

- `SKILL.md`: this file
- `references/search-map.md`: concept-to-regex table for step 5, with notes on
  extending it

## Attribution

Built by Korey Dillon (LatentAxis). Extracted from cipher-harness, a minimal,
hackable terminal coding agent: https://github.com/koreydillon/cipher-harness.
More at https://latentaxis.io
