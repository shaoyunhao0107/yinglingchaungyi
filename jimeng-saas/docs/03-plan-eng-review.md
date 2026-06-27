# /plan-eng-review — Jimeng SaaS

> Engineering architecture review. Mode: **HOLD SCOPE** (max rigor on the
> CEO-approved scope). Locks architecture, data model, service boundaries,
> failure modes. Output feeds `/spec`.
> Input: `docs/02-plan-ceo-review.md`.

---

## Architecture principles

1. **Reuse the user's familiar stack** (FastAPI + SQLModel + Jinja2 + Linear
   dark UI — same as the AI 账号管理系统). Minimize new tech to learn.
2. **Provider-abstracted from day 1.** `GenerationProvider` interface; 即梦
   is the first implementation, not hardcoded everywhere.
3. **Async job pipeline.** Image gen is 10–60s, video is 30s–5min. Never
   block the HTTP request. Job queue + worker + SSE/websocket push.
4. **sessionid pool is first-class infra**, not an afterthought. Health
   checks, rate-limiting per sessionid, graceful degradation.
5. **Artifacts persisted to object storage**, never proxied from byteimg.com.
   URLs expire.
6. **SaaS concerns layered on top of the CRUD base**: users, quota, billing,
   multi-tenant isolation — without bloating the core CRUD primitives.

---

## Stack decisions (locked)

| Layer | Pick | Rationale |
|---|---|---|
| Web framework | **FastAPI** | User familiar; async; Form() parsing concise |
| ORM | **SQLModel** | User familiar; Pydantic + SQLAlchemy in one |
| DB | **PostgreSQL** (prod) / **SQLite** (dev) via `JSA_DB_URL` | Multi-user concurrency → PostgreSQL required; SQLite for dev only. Same dual-engine pattern as AI 账号管理系统 (Pitfall #18) |
| Templates | **Jinja2** for chrome (nav, library, billing, settings) | User familiar; server-rendered is correct for these |
| Interactive islands | **HTMX + Alpine.js** (NOT React) | Minimal JS payload; no build step; pairs naturally with Jinja2. Used for: generation canvas, live job progress, image grid selection, batch prompt entry. |
| Background jobs | **RQ (Redis Queue)** + **redis** | Simplest Python async queue; lighter than Celery; survives restart; great observability. Image gen is I/O-bound (HTTP to即梦), RQ is right-sized. |
| Object storage | **Local filesystem** (dev + small部署) → **S3/R2** (prod) via `STORAGE_BACKEND` env | Start local (`/data/artifacts/{user_id}/...`), swap to R2 when scale demands. Abstracted behind a `Storage` interface. |
| Auth | **JWT access + refresh tokens** (NOT session cookies) | SaaS — clients may include mobile / API; JWT is stateless + scalable. Cookies for the web UI, bearer for API. |
| Secrets | **Fernet encryption** (same as AI 账号管理系统) | sessionids are encrypted at rest; master key in env. |
| Styling | **Linear dark UI** (same as AI 账号管理系统) | User familiar; consistent visual language across their products. |
| Deployment | **Docker Compose** (app + worker + redis + postgres) | Single-command prod deploy. |

---

## Service topology

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (user)                          │
└─────────────────────────────────────────────────────────────┘
                          │   ↑
              HTTPS (JWT) │   │ SSE/WebSocket (job progress)
                          ▼   │
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI app (web + API)                    │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐ │
│  │ Auth (JWT)   │ │ Generation   │ │ Library / Folders / │ │
│  │ Users        │ │ Canvas (HTMX)│ │ Templates / Billing │ │
│  │ Quota        │ │ Batch CSV    │ │ (Jinja2)            │ │
│  └──────────────┘ └──────────────┘ └─────────────────────┘ │
│              │ enqueue                                ↑    │
│              ▼                                       │    │
│  ┌──────────────────────────┐                        │    │
│  │  RQ Queue (Redis)        │                        │    │
│  └──────────────────────────┘                        │    │
│              │                                       │    │
│              ▼                                       │    │
│  ┌──────────────────────────┐   SSE push ────────────┘    │
│  │  RQ Worker(s)            │                              │
│  │  - calls Provider        │                              │
│  │  - downloads artifacts   │                              │
│  │  - updates DB            │                              │
│  └──────────────────────────┘                              │
└─────────────────────────────────────────────────────────────┘
        │                                  │
        ▼                                  ▼
┌────────────────┐               ┌────────────────────┐
│ JimengProvider  │               │ Storage            │
│ (self-hosted)   │               │ (local / S3 / R2)  │
│ - sessionid pool│               └────────────────────┘
│ - health check  │
│ - rate limit    │
└────────────────┘
        │
        ▼
   即梦 upstream
```

---

## Provider abstraction (the moat)

```python
class GenerationProvider(ABC):
    """A pluggable AI generation backend."""

    @abstractmethod
    async def health_check(self) -> ProviderHealth: ...

    @abstractmethod
    async def generate_images(self, req: ImageGenRequest, credential: Credential) -> list[Artifact]: ...

    @abstractmethod
    async def generate_videos(self, req: VideoGenRequest, credential: Credential) -> list[Artifact]: ...

    @abstractmethod
    def supported_models(self) -> list[ModelInfo]: ...
```

- `JimengProvider` implements this; the sessionid pool lives inside it.
- v2.5 adds `MidjourneyProvider`, `SDProvider` — same interface.
- Routes call `provider = get_provider(req.provider_name)` — never hardcode.

---

## Data model (v1)

Core entities. All get `id`, `created_at`, `updated_at`, `deleted_at` (soft-delete from day 1, Pitfall #12 of python-web-crud-app).

### `users`
- `id, email, password_hash, name, plan_tier (free/pro/team), quota_used, quota_limit, stripe_customer_id (v2), created_at`
- Indexes: `email` unique.

### `api_keys` (v1.5 — for public API)
- `id, user_id, key_hash, name, last_used_at, revoked_at`

### `provider_credentials` (the sessionid pool)
- `id, provider_name ('jimeng'), region ('cn'|'us'|'hk'|'jp'|'sg'), sessionid_enc, status ('healthy'|'exhausted'|'banned'|'cooldown'), last_health_at, daily_calls, daily_calls_reset_at, notes`
- **Encrypted** with Fernet master key.
- Indexes: `(provider_name, status)` for pool selection.

### `generation_jobs`
- `id, user_id, provider_name, job_type ('image'|'video'), status ('queued'|'running'|'succeeded'|'failed'|'cancelled'), prompt, params_json, parent_job_id (for variation tree), credential_id_used, error_message, started_at, completed_at, variation_count`
- Indexes: `(user_id, status, created_at)`, `(status)` for worker queue.

### `artifacts`
- `id, job_id, user_id, kind ('image'|'video'), storage_url (own storage), source_url (upstream, for debug), width, height, duration_secs (video), bytes_size, thumbnail_url, content_hash (sha256, for dedup)`
- Indexes: `(user_id, created_at)`, `(job_id)`, `(content_hash)`.

### `folders`
- `id, user_id, name, parent_id (nullable, for nesting), color, sort_order`
- Indexes: `(user_id, parent_id)`.

### `artifacts_folders` (many-to-many)
- `artifact_id, folder_id, added_at`

### `tags`
- `id, user_id, name, color`

### `artifacts_tags` (many-to-many)
- `artifact_id, tag_id`

### `templates` (v1.5 placeholder — schema now, UI later)
- `id, user_id, name, provider_name, model, ratio, resolution, negative_prompt, style_prefix, output_folder_id, created_at, last_used_at`

### `quota_events` (audit trail for billing)
- `id, user_id, event_type ('image_gen'|'video_gen'|'storage'), quantity, cost_credits, job_id, created_at`
- Indexes: `(user_id, created_at)`.

### `audit_log` (security)
- `id, user_id, action, target_type, target_id, ip, user_agent, created_at`

---

## Job lifecycle (the critical async path)

```
1. User submits batch → POST /api/jobs (N prompts × params)
2. Server validates quota, creates N `generation_jobs` (status=queued),
   enqueues each to RQ. Returns 202 + job_ids immediately.
3. Worker pops job:
   a. status → running
   b. Acquire healthy credential from pool (rate-limit aware)
   c. Call JimengProvider.generate_images() with timeout=300s
   d. On success: download each returned URL → save to Storage →
      create `artifacts` rows → status=succeeded
   e. On credential failure: mark credential exhausted, retry with another
   f. On all-credentials-exhausted: status=failed, alert ops
   g. status → succeeded/failed, completed_at set
4. SSE push to user's browser: "job X done, +4 images"
5. Quota debited via `quota_events` on success only
```

**Failure modes handled**:
- Credential exhausted → pool failover (max 3 retries across credentials).
- Upstream timeout → retry once; second timeout → mark job failed, user not charged.
- Storage write fails → rollback job to `running`, alert ops.
- Worker crash mid-job → RQ job visibility timeout returns it to queue, idempotent retry via `content_hash` dedup.

---

## Routes (v1)

### Auth
- `POST /api/auth/register` — email + password (rate-limited, captcha v2)
- `POST /api/auth/login` — returns access + refresh JWT
- `POST /api/auth/refresh`
- `GET  /login`, `GET /register` — Jinja2 pages

### Jobs (API)
- `POST /api/jobs` — create one or many (batch). Body: `[{prompt, type, params}]` or CSV upload.
- `GET  /api/jobs` — list (filter by status, type, date)
- `GET  /api/jobs/{id}` — detail (includes artifacts)
- `POST /api/jobs/{id}/cancel`
- `POST /api/jobs/{id}/iterate` — variation tree: creates child job with `parent_job_id=this`, pre-fills prompt + params, optional `modify_prompt` field.
- `GET  /api/jobs/stream` — SSE: live updates for the current user's jobs

### Artifacts / Library (API + Jinja2)
- `GET /api/artifacts` — list, filter by folder/tag/date, full-text search on prompt (via prompts join)
- `PATCH /api/artifacts/{id}` — rename, add tags, move folder
- `DELETE /api/artifacts/{id}` — soft-delete
- `GET /api/artifacts/{id}/download` — signed URL to own storage
- `POST /api/artifacts/batch-export` — zip + rename per pattern

### Folders / Tags (API)
- CRUD endpoints, user-scoped

### Templates (v1.5)
- CRUD endpoints

### Billing (v1 minimal, v2 Stripe)
- `GET /billing` — Jinja2 page showing plan, usage, upgrade CTA
- `POST /billing/checkout` — v2: Stripe checkout session

### Admin (ops only — separate role)
- `GET /admin/credentials` — sessionid pool health dashboard
- `POST /admin/credentials` — add new sessionid (encrypted at rest)
- `POST /admin/credentials/{id}/refresh` — re-health-check
- `GET /admin/jobs` — all jobs, all users

### Pages (Jinja2)
- `/` — dashboard: recent jobs, quota usage, quick-action
- `/generate` — generation canvas (HTMX island): prompt entry (textarea for batch), model/ratio/resolution pickers, CSV upload, live progress
- `/library` — artifact grid with folder sidebar + tag filter + search
- `/library/{id}` — artifact detail: image, prompt, params, variations tree, "iterate" button, folder/tag controls
- `/folders/{id}` — folder view
- `/templates` — v1.5
- `/billing`
- `/settings` — profile, password, API keys (v1.5)
- `/admin/*` — admin pages

---

## Hybrid rendering plan (which page is what)

| Page | Rendering | Why |
|---|---|---|
| `/login`, `/register` | Jinja2 standalone (no nav) | Linear-style auth card, no interactivity |
| `/` dashboard | Jinja2 + tiny HTMX for quota refresh | Mostly static, one poll |
| `/generate` canvas | Jinja2 shell + **HTMX/Alpine heavy island** | Live progress, prompt textarea, model picker, image grid — highly interactive |
| `/library` grid | Jinja2 + HTMX for filter/pagination | Filter changes → HTMX swap, no full reload |
| `/library/{id}` | Jinja2 + Alpine for tag editing | One interactive affordance |
| `/billing`, `/settings`, `/admin/*` | Pure Jinja2 | Forms + tables, server-rendered is correct |

**JS payload budget**: HTMX (14kb gz) + Alpine (10kb gz) + tiny app-specific JS (~5kb). **No React, no build step, no node_modules in production.** Matches the user's existing stack.

---

## Security model

1. **Passwords**: bcrypt via `passlib[bcrypt]`.
2. **JWT**: access token 15min, refresh 30d, rotation on use.
3. **sessionid storage**: Fernet-encrypted in `provider_credentials.sessionid_enc`. Master key in `JSA_MASTER_KEY` env, never logged.
4. **Multi-tenant isolation**: every query filters `WHERE user_id = :current_user_id`. Admin role bypasses. Row-level tests required.
5. **Upload safety**: user-uploaded images (for image-to-image) scanned + size-limited (10MB) + served from a sandboxed path.
6. **Rate limiting**: per-user (10 jobs/min) + per-IP (100 req/min) via `slowapi`.
7. **CSRF**: JWT in `Authorization` header avoids CSRF; web UI uses SameSite=Strict cookies for the refresh token.
8. **Audit log**: every credential access, every admin action, every billing change → `audit_log`.

---

## Quota & pricing model (v1)

Each generation consumes **credits**:

| Action | Credits |
|---|---|
| 1 image generation (batch of 4) | 1 |
| 1 video generation | 5 |

Plan tiers:

| Plan | Monthly price | Credits/mo | Notes |
|---|---|---|---|
| Free | ¥0 | 10 | For trial; watermark in library |
| Hobby | ¥29 | 100 | Most individual creators |
| Pro | ¥99 | 500 | Heavy users, batch CSV, templates |
| Team | ¥299+ | 2000+ | v2: multi-seat, shared library |

Credits deducted **on success only** (failed gens are free). Roll over up to 1 month. Track every deduction in `quota_events`.

---

## Failure modes & on-call

| Failure | Detection | Mitigation |
|---|---|---|
| sessionid expired | Provider returns 401 | Mark credential `exhausted`, alert ops to replenish |
| Upstream即梦 changes API | Worker raises parse error | Alert; engineer pulls latest iptag/jimeng-api + updates JimengProvider |
| Storage full | Storage write raises | Alert; reject new jobs until resolved |
| Worker backlog > 1000 jobs | RQ queue depth metric | Auto-scale workers (docker compose `--scale worker=N`) |
| DB connection exhaustion | Pool timeout | Alert; investigate slow queries |
| User quota race | DB constraint on `quota_events` sum | Serialize via advisory lock on user_id |

---

## Deferred (NOT v1, but architecture must allow)

- **Video generation** (v1.5): same job pipeline, different timeout + UI. Already in DB schema.
- **Template engine** (v1.5): `templates` table exists; UI deferred.
- **Team workspaces** (v2): add `workspace_id` to all user-scoped tables; migration.
- **Multi-provider** (v2.5): `GenerationProvider` interface ready; new providers are additive.
- **Public API** (v1.5): `api_keys` table; rate-limit per key.
- **Stripe billing** (v2): `stripe_customer_id` column exists; webhook handlers.

---

## Open questions for `/spec`

1. Exact即梦 endpoint URLs + payload shapes (need to read jimeng-api source in depth — this is the JimengProvider contract).
2. STorage layout: `/data/artifacts/{user_id}/{yyyy}/{mm}/{job_id}/{variant_n}.png` — confirm path scheme.
3. Worker count: start with 2, scale on backlog?
4. sessionid pool starting size: how many does the user have available for launch?
5. Captcha for register: hCaptcha vs. Cloudflare Turnstile (Turnstile is free + no-tracking).
