# Concept search map

Step 5 of the orientation procedure turns a concept from the task description
into a set of regular expressions, searches for all of them, and ranks files by
how many lines hit. This file is the table. Patterns are language-agnostic
where possible and lean toward recall; a few extra hits are cheaper than a
miss.

## How to use it

1. Find the row whose concept words appear in the task. Match loosely:
   "errors", "exception handling", and "failure path" all map to
   **error handling**.
2. Join the row's patterns with `|` into one alternation.
3. Search the source tree, excluding generated and vendored directories.
4. Count hits per file, sort descending, read the top two or three.
5. Add two or three distinctive words from the task itself as extra patterns
   (a product name, a table name, an endpoint path). Those usually sharpen the
   ranking more than the generic row does.

Unix shell:

```bash
grep -rnEi --include='*.py' --include='*.ts' --include='*.go' \
  --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist \
  'PATTERN_A|PATTERN_B|PATTERN_C' . \
  | cut -d: -f1 | sort | uniq -c | sort -rn | head -10
```

With ripgrep, which respects `.gitignore` automatically:

```bash
rg -c -i 'PATTERN_A|PATTERN_B|PATTERN_C' | sort -t: -k2 -rn | head -10
```

PowerShell:

```powershell
Get-ChildItem -Recurse -Include *.py,*.ts,*.go |
  Where-Object { $_.FullName -notmatch '\\(node_modules|\.git|dist)\\' } |
  Select-String -Pattern 'PATTERN_A|PATTERN_B|PATTERN_C' |
  Group-Object Path | Sort-Object Count -Descending |
  Select-Object -First 10 Count, Name
```

## The map

| Concept | Patterns |
|---|---|
| error handling | `try:` `except\s` `catch\s*\(` `\.catch\(` `raise\s` `throw\s` `rescue\b` `Result<` `if err != nil` |
| database | `SELECT\s` `INSERT\s` `UPDATE\s` `DELETE\s` `CREATE TABLE` `\.query\(` `\.execute\(` `cursor` `Session\(` `prisma\.` `knex\(` `sqlx::` `gorm\.` |
| migrations | `migrat` `alembic` `schema_migrations` `AddColumn` `CreateTable` `up\(\)` `down\(\)` |
| authentication | `login` `logout` `\bauth` `token` `jwt` `password` `session` `cookie` `oauth` `bcrypt` `argon2` |
| authorization | `permission` `role` `is_admin` `can_\w+` `policy` `scope` `rbac` `acl` |
| api | `@app\.(get\|post\|put\|delete\|patch)` `@router\.` `router\.` `endpoint` `@route` `@(Get\|Post\|Put\|Delete)Mapping` `http\.HandleFunc` `fetch\(` `axios\.` `requests\.(get\|post)` |
| webhook | `webhook` `signature` `HMAC` `X-Hub-Signature` `Stripe-Signature` `verify_signature` |
| background jobs | `celery` `@task` `@shared_task` `sidekiq` `perform_async` `bull` `Queue\(` `cron` `schedule` `worker` |
| testing | `def test_` `assert\s` `expect\(` `describe\(` `it\(` `pytest` `unittest` `#\[test\]` `func Test` `@Test` |
| logging | `logger\.` `logging\.` `console\.(log\|warn\|error)` `log\.(info\|debug\|warn\|error)` `slog\.` `tracing::` |
| config | `os\.environ` `getenv` `\.env` `config\[` `settings\.` `process\.env` `viper\.` `dotenv` `ConfigParser` |
| validation | `validate` `validator` `schema` `pydantic` `zod` `joi` `yup` `marshmallow` `serializer` |
| async | `async\s+def` `await\s` `asyncio` `Promise` `\.then\(` `go func` `tokio::` `Future<` |
| file io | `open\(` `readFile` `writeFile` `os\.path` `pathlib` `fs\.` `ioutil` `os\.ReadFile` `File::` |
| network | `socket` `http\.client` `urllib` `requests\.` `fetch\(` `net/http` `reqwest` `websocket` |
| caching | `cache` `redis` `memcache` `lru_cache` `@cached` `TTL` `etag` |
| security | `hash` `encrypt` `decrypt` `sanitize` `escape` `cors` `csrf` `xss` `secret` `nonce` `hmac` |
| payments | `stripe` `paypal` `braintree` `charge` `invoice` `subscription` `checkout` `payment_intent` |
| email | `smtp` `sendmail` `send_mail` `mailer` `sendgrid` `postmark` `ses\.` `EmailMessage` |
| cli | `argparse` `click\.` `typer` `commander` `yargs` `cobra` `clap::` `sys\.argv` `process\.argv` |
| state management | `useState` `useReducer` `redux` `zustand` `store\.` `dispatch\(` `Vuex` `Pinia` `signal\(` |
| routing (frontend) | `<Route` `useRouter` `createBrowserRouter` `next/router` `next/navigation` `vue-router` `\$router` |
| models or entities | `class \w+\(models\.Model\)` `class \w+\(Base\)` `@Entity` `@Table` `type \w+ struct` `model \w+ \{` `struct \w+ \{` |
| feature flags | `feature_flag` `isEnabled\(` `launchdarkly` `unleash` `flags\.` `FEATURE_` |
| rate limiting | `rate_limit` `ratelimit` `throttle` `RateLimiter` `429` `Retry-After` |
| retries | `retry` `backoff` `tenacity` `max_attempts` `exponential` `p-retry` |
| i18n | `i18n` `gettext` `_\(` `translate` `locale` `intl` `useTranslation` |

## Extending the map

- Add a row when the same concept comes up twice in a project. Keep the row to
  five to ten patterns.
- Prefer patterns that are stable across languages (`webhook`, `retry`) over
  library names that change. Add library names second.
- Escape regex metacharacters. A literal dot is `\.`, a literal parenthesis is
  `\(`.
- If a project has its own vocabulary (a service called `ledger`, a table
  called `fulfillment_events`), keep a project-local row in the project's
  notes or memory rather than editing this file.
