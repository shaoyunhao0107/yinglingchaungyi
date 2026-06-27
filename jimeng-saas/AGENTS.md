# Jimeng SaaS — Agent Guide

> Read this before any work on this repo. Pair with `docs/SPEC.md` (build blueprint)
> and `DESIGN.md` (visual source of truth).

## What this project is

**即梦创意工作站** — a paid SaaS that gives Chinese content creators (公众号作者/设计师/电商运营)
a fast batch AI image/video generation workspace with persistent library, folders,
tags, and variation trees. Powered by self-hosted Jimeng API (reverse-engineered).
The backend owns the sessionid pool; users never see it.

## Skill routing (when working in this repo)

- Product decisions / scope questions → re-read `docs/02-plan-ceo-review.md`
- Architecture / data flow / service boundaries → `docs/03-plan-eng-review.md`
- Any UI / color / typography / motion choice → `DESIGN.md` is source of truth, **do not deviate**
- Bug investigation → `/investigate`
- Pre-commit review → `/review`
- Visual QA on `http://localhost:8000` → `/qa`
- Ship a PR → `/ship`

## Hard rules (non-negotiable)

1. **Multi-tenant isolation.** Every DB query that touches user-scoped tables (`artifacts`,
   `folders`, `tags`, `generation_jobs`, `templates`) MUST filter by `user_id`. Tests in
   `tests/test_api_isolation.py` enforce this. Never write `select(Artifact)` without
   `.where(Artifact.user_id == current_user.id)`.

2. **Never log sessionids.** Even encrypted. Use `[REDACTED]` in any log line that might
   touch `provider_credentials.sessionid_enc`. Audit-log access instead.

3. **Field-set symmetry.** When adding any field to a model, update ALL of these in the
   same edit pass: `models/`, `schemas/`, `routes/`, templates, export. Half-implemented
   fields are bugs. (Same lesson as python-web-crud-app Pitfall #7.)

4. **CSS variables match DESIGN.md exactly.** No `--card`, no `--muted`. Use `--bg-elevated`,
   `--text-tertiary`, etc. The full canonical list is in DESIGN.md §Color. Grep-verify
   before declaring UI done:
   ```bash
   grep -rhoE 'var\(--[a-z0-9-]+\)' app/templates/ | sort -u
   # Every entry MUST exist in app/static/style.css :root
   ```

5. **Generation is always async.** Never block an HTTP request on a provider call. POST
   `/api/jobs` returns 202 immediately; the worker runs the provider; SSE pushes status.
   Image gen takes 10–60s, video 30s–5min — these are not request-budget times.

6. **Failed jobs do not debit quota.** Ever. The worker calls `quota.debit()` only on
   success. If you find a path that debits before confirming success, that's a bug.

7. **Artifacts are persisted to our own storage, never proxied.** Upstream byteimg.com
   URLs expire. The worker downloads every artifact via `storage.download_and_store()`
   before marking a job succeeded.

8. **sessionid pool is the moat.** Treat `provider_credentials` as critical infra:
   health-check before every acquire, mark `exhausted` on 401, alert ops. A single
   sessionid is a single point of failure — always design for pool failover.

9. **Provider-abstracted.** Routes call `get_provider(name)` — never import
   `JimengProvider` directly outside `providers/`. v2.5 will add `MidjourneyProvider`;
   the architecture must allow that without touching routes.

10. **Chinese-first UX.** All copy defaults to 中文. Error messages, placeholders,
    empty states — all Chinese first. English is optional secondary.

## Working directory conventions

- Python interpreter: `C:\Program Files\Python310\python.exe` (3.10.8 — same as AI 账号管理系统)
- Run in dev: `run.bat` (sets env, launches uvicorn on :8000 with --reload OFF for verification — see python-web-crud-app Pitfall #20)
- Worker: `worker.bat` (separate window, RQ worker on `jimeng` queue)
- Dev DB: `data/jimeng.db` (SQLite). Prod: PostgreSQL via `JSA_DB_URL`.
- Env: copy `.env.example` to `.env`, fill in `JSA_SECRET_KEY`, `JSA_MASTER_KEY`, `JSA_JIMENG_UPSTREAM`.

## Windows-specific gotchas (collected during Week 1 bring-up)

1. **`bcrypt` 5.x breaks `passlib`.** Symptom: `AttributeError: module 'bcrypt' has no attribute '__about__'` on first `hash_password()`. Fix: pin `bcrypt<4.1` (we use 4.0.1). Add to requirements.txt explicitly.

2. **RQ default worker uses `os.fork()` — not on Windows.** Symptom: worker crashes on first job with `AttributeError: module 'os' has no attribute 'fork'`. Fix: always use `rq.worker.SimpleWorker` (no fork, runs job in main process). `worker.bat` already does this via `--worker-class "rq.worker.SimpleWorker"`.

3. **RQ CLI entry point is `rq.cli`, not `rq`.** `python -m rq worker` → `No module named rq.__main__`. Use `python -m rq.cli worker ...`.

4. **Email validation requires a dot in the domain.** `admin@local` fails Pydantic `EmailStr` (`The part after the @-sign is not valid. It should have a period.`). Use `admin@example.com` (or any dotted domain) for seed accounts.

5. **Memurai (not Redis) for Windows.** Real Redis doesn't ship native Windows binaries. Install via `winget install Memurai.MemuraiDeveloper` — it's Redis-compatible, runs as a Windows service on :6379, `memurai-cli` is the CLI. `PING` → `PONG` confirms.

6. **`.env` is NOT auto-loaded by uvicorn.** Either `set -a && source .env && set +a` before launching, or use `python-dotgrid` in `config.py`. Our `run.bat` / `worker.bat` source it via a `for /f` loop.

7. **Stale RQ WIP lock after a worker crash.** When the fork-fail crashed the first worker mid-job, the job stayed in `rq:wip:jimeng` and the new worker couldn't pick it up. Clear via `memurai-cli del rq:wip:jimeng rq:executions:<id> rq:job:<id>`, then re-enqueue.

8. **Path param route shadowing — `@app.post("/api/jobs/{id}/cancel")` is fine**, but if you add `@app.post("/api/jobs/batch")` AFTER it, FastAPI matches in declaration order and `batch` gets parsed as `int` for `{id}`. Declare specific paths before parameterized ones, or use a non-colliding prefix. (We avoided this; documenting for future routes.)

## Verification checklist before declaring any feature done

- [ ] Unit tests pass (`pytest tests/`)
- [ ] `curl` smoke-test of the new endpoint returns expected status code + body
- [ ] Browser smoke-test: the page renders without console errors
- [ ] Multi-tenant check: log in as user B, confirm user A's data is invisible
- [ ] CSS variables grep: no undefined `var(--xxx)` in templates
- [ ] Failed-path handled: what happens if the provider 500s? if pool exhausted? if storage full?
- [ ] Chinese copy reviewed (no English leaking into user-facing strings)
- [ ] Quota correctly debited ONLY on success (manual DB check after a test run)

## See also

- `docs/SPEC.md` — the full build blueprint (file layout, schema, API, week-by-week plan)
- `DESIGN.md` — visual design system (Studio Dark + aurora accent)
- `docs/01-office-hours.md` — product rationale (the "why")
- `docs/02-plan-ceo-review.md` — strategic decisions + 10-star vision
- `docs/03-plan-eng-review.md` — architecture rationale + failure modes
