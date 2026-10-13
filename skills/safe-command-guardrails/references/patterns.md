# Command patterns by tier

These are the regular expressions used by `scripts/check_command.py`. They are
also the mental checklist an agent should apply when no script is wired in.
All patterns are matched case-insensitively against the full command string.

If you change a pattern here, change it in the script too. The script's
`--self-test` flag will tell you if a change broke an expected result.

## Design rules

- Favor false negatives over false positives in CONFIRM. A missed confirm costs
  one bad command. A noisy confirm trains the user to say yes without reading.
- BLOCK is reserved for damage that no project context can justify.
- SECRET is about exposure, not use. Passing a token in an `Authorization`
  header to the service that issued it is normal. Printing it, staging it, or
  uploading it is not.
- Quoted strings are treated as data only when the command is a single
  read-only command (`grep`, `echo`, `cat`, `git log`, and similar) with no
  pipes, chaining, or substitution. So `grep "rm -rf /" docs/` is ALLOW while
  `bash -c "rm -rf /"` is BLOCK.

## Tier 1: BLOCK

Never run. Do not offer an override. Explain why and suggest a narrower command.

| Pattern | Catches |
|---|---|
| `\brm\s+(?:-{1,2}\S+\s+)*(?:/\|/\*\|~\|~/\|\$HOME/?)(?=\s\|$\|["';&\|])` | `rm -rf /`, `rm -rf ~`, `rm -rf $HOME` |
| `--no-preserve-root` | any rm with the safety flag disabled |
| `:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:` | fork bomb |
| `\bmkfs(?:\.\w+)?\b` | formatting a filesystem |
| `\bdd\b[^\|;&]*\bof=/dev/(?:sd\|hd\|nvme\|disk\|mmcblk)` | raw write to a disk |
| `>\s*/dev/(?:sd\|hd\|nvme\|disk\|mmcblk)\w*` | redirecting output onto a disk |
| `\bshred\b[^\|;&]*/dev/` | shredding a device |
| `\bchmod\s+(?:-R\s+\|--recursive\s+)?[0-7]{3,4}\s+/(?=\s\|$\|["';&\|])` | permission change on root |
| `\bchown\s+-R\s+\S+\s+/(?=\s\|$\|["';&\|])` | ownership change on root |
| `\bformat\s+[a-z]:` | Windows drive format |
| `\bFormat-Volume\b` | PowerShell volume format |
| `\bRemove-Item\b[^\|;]*\s(?:[A-Za-z]:\\\|\\)\s*(?:-\|$)` | Remove-Item on a drive root |

## Tier 2: SECRET

Treated like BLOCK in the script (hook decision `deny`). The agent should stop,
tell the user what would have leaked, and propose a version that does not
expose the value.

### Literal credentials anywhere in the command

| Pattern | Catches |
|---|---|
| `sk-ant-[A-Za-z0-9_-]{10,}` | Anthropic key |
| `\bsk-(?:proj-)?[A-Za-z0-9]{20,}` | OpenAI style key |
| `\bAKIA[0-9A-Z]{16}\b` | AWS access key id |
| `\bghp_[A-Za-z0-9]{30,}\b` | GitHub classic token |
| `\bgithub_pat_[A-Za-z0-9_]{20,}\b` | GitHub fine-grained token |
| `\bxox[baprs]-[A-Za-z0-9-]{10,}\b` | Slack token |
| `-----BEGIN (?:RSA \|EC \|OPENSSH \|DSA )?PRIVATE KEY-----` | private key material |

### Secret-bearing environment variables in a display context

Variable names: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AWS_SECRET_ACCESS_KEY`,
`AWS_SESSION_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, `DATABASE_URL`, `DB_PASSWORD`,
`POSTGRES_PASSWORD`, `MYSQL_PWD`, `STRIPE_SECRET_KEY`, `SLACK_BOT_TOKEN`,
`NPM_TOKEN`, `PYPI_TOKEN`, `TWINE_PASSWORD`, and anything containing `SECRET`.

| Pattern | Catches |
|---|---|
| `\b(?:echo\|printf\|printenv)\b[^\|;&]*\$\{?<NAME>` | `echo $ANTHROPIC_API_KEY` |

### Secret files in a staging or upload context

Secret files: `.env` and `.env.*` (except `.example`, `.sample`, `.template`,
`.dist`), `id_rsa`, `id_ed25519`, `id_ecdsa`, `*.pem`, `credentials.json`,
`.npmrc`, `.pypirc`.

| Pattern | Catches |
|---|---|
| `\bgit\s+add\b[^\|;&]*<SECRET_FILE>` | `git add .env` |
| `\b(?:curl\|wget)\b[^\|;&]*(?:-F\|--form\|-d\|--data\S*\|-T\|--upload-file)\s*\S*@?<SECRET_FILE>` | uploading a secrets file |
| `\bgit\s+add\s+(?:-A\|--all\|\.)(?:\s\|$)` | blanket staging that may sweep in secrets |
| `\bgit\s+commit\b[^\|;&]*<SECRET_FILE>` | `git commit .env` (see note) |
| `\b(?:scp\|rsync\|sftp)\s+(?:(?!--exclude)[^\|;&\s]+\s+)*?(?:\S*/)?<SECRET_FILE>(?=\s\|$)` | `scp .env host:`; an `--exclude .env` argument does not count |

Note on `git commit`: before the SECRET context check runs, the script replaces
the argument of `-m`, `-am`, and `--message` with a placeholder. So
`git commit -m "fix .env loading"` is ALLOW while `git commit .env -m "x"` is
SECRET. The replacement is only used for this tier.

## Tier 3: CONFIRM

Show the exact command and the reason, then wait for an explicit yes.

### Files and system

| Pattern | Reason |
|---|---|
| `\brm\s+(?:-{1,2}\S+\s+)*-[A-Za-z]*[rR][A-Za-z]*\b` | recursive delete |
| `\brm\s+(?:-\S+\s+)*--recursive\b` | recursive delete |
| `\bRemove-Item\b[^\|;]*-Recurse\b` | recursive delete (PowerShell) |
| `\b(?:rd\|rmdir)\s+/s\b` | recursive delete (cmd) |
| `\bdel\s+(?:/\w\s+)*/[sq]\b` | bulk delete (cmd) |
| `\bchmod\s+(?:-R\s+\|--recursive\s+)?777\b` | world-writable permissions |
| `\bsudo\s+(?:rm\|chmod\|chown\|dd\|mv\|mkfs)\b` | elevated destructive command |
| `>\s*/etc/` | overwrites system configuration |
| `\bcrontab\s+-r\b` | removes all cron jobs |
| `\b(?:kill\s+-9\s+-1\|killall\b)` | kills many processes |
| `\b(?:curl\|wget)\b[^\|]*\|\s*(?:sudo\s+)?(?:ba\|z\|da\|k)?sh\b` | pipes a remote script into a shell |
| `\b(?:cat\|less\|more\|head\|tail\|type\|Get-Content)\s+[^\|;&]*<SECRET_FILE>` | prints a secrets file into the transcript |
| `\b(?:cp\|mv)\s+(?:-\S+\s+)*(?:\S*/)?<SECRET_FILE>(?=\s\|$)` | copies or moves a secrets file; `cp .env.example .env` is ALLOW because only the source is checked |

### Git

| Pattern | Reason |
|---|---|
| `\bgit\s+push\b[^\|;&]*(?:\s--force\b\|\s-f\b)` | force push |
| `\bgit\s+push\b` | any push is visible to others |
| `\bgit\s+reset\s+--hard\b` | discards uncommitted work |
| `\bgit\s+clean\b[^\|;&]*-[A-Za-z]*[dfx]` | deletes untracked files |
| `\bgit\s+(?:checkout\|restore)\s+(?:--\s+)?\.(?:\s\|$)` | discards all working tree changes |
| `\bgit\s+branch\s+(?:-D\|--delete\s+--force)\b` | force-deletes a branch |
| `\bgit\s+stash\s+(?:drop\|clear)\b` | drops stashed work |
| `\bgit\s+rebase\b` | rewrites history |
| `\bgit\s+commit\b[^\|;&]*--amend\b` | rewrites the last commit |

### Databases

| Pattern | Reason |
|---|---|
| `\bDROP\s+(?:TABLE\|DATABASE\|SCHEMA\|INDEX\|VIEW)\b` | destroys data or structure |
| `\bTRUNCATE\s+(?:TABLE\s+)?\w` | deletes all rows |
| `\bDELETE\s+FROM\s+[\w."`\[\]]+\s*;?\s*$` | DELETE without WHERE |
| `\bUPDATE\s+[\w."`\[\]]+\s+SET\b(?![\s\S]*\bWHERE\b)` | UPDATE without WHERE |
| `\bALTER\s+TABLE\b[^;]*\bDROP\s+(?:COLUMN\|CONSTRAINT)\b` | irreversible schema change |
| `\b(?:dropdb\|mongo\S*\s+.*\.drop(?:Database)?\(\|redis-cli\s+(?:-\S+\s+)*FLUSH(?:ALL\|DB))` | drops a whole database |

### Containers, infrastructure, cloud

| Pattern | Reason |
|---|---|
| `\bdocker\s+(?:system\|volume\|image\|container\|network)\s+prune\b` | docker prune |
| `\bdocker\s+(?:volume\s+rm\|rm\s+-f\|rmi\s+-f)\b` | removes docker resources |
| `\bdocker[- ]compose\s+down\b[^\|;&]*(?:-v\|--volumes)\b` | deletes compose volumes |
| `\bterraform\s+(?:destroy\|apply\s+[^\|;&]*-auto-approve)\b` | destroy or unattended apply |
| `\bkubectl\s+delete\b` | kubectl delete |
| `\bhelm\s+(?:uninstall\|delete)\b` | helm uninstall |
| `\baws\s+s3\s+(?:rm\|rb)\b` | deletes S3 objects or buckets |
| `\baws\s+\S+\s+(?:delete\|terminate)-[a-z-]+\b` | AWS delete or terminate |
| `\b(?:gcloud\|az)\s+[^\|;&]*\s+delete\b` | cloud resource delete |

### Publishing and outward-facing actions

| Pattern | Reason |
|---|---|
| `\b(?:npm\|pnpm\|yarn)\s+publish\b` | publishes a package |
| `\b(?:twine\s+upload\|poetry\s+publish\|cargo\s+publish\|gem\s+push\|dotnet\s+nuget\s+push)\b` | publishes a package |
| `\bgh\s+(?:pr\|release)\s+create\b` | creates a public PR or release |
| `\bgh\s+repo\s+(?:delete\|create)\b` | creates or deletes a repository |

## Tuning

- Too noisy? Delete the `git push` row and the `git rebase` row first. They are
  the most common complaints and the least dangerous entries in CONFIRM.
- Working in a sandbox with disposable data? Move the database rows from
  CONFIRM to a project-local allowlist and leave the rest.
- Need project-specific blocks (a production hostname, a deploy script)? Add
  them to BLOCK. Keep each pattern anchored to a command name so it does not
  fire on prose in commit messages or grep arguments.
- After any edit, run `python3 scripts/check_command.py --self-test`.
