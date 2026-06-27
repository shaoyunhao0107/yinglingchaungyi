# SPEC — Jimeng SaaS (即梦创意工作站)

> Authoritative build spec. Everything below is implementation-ready.
> Inputs: `docs/01-office-hours.md`, `docs/02-plan-ceo-review.md`,
> `docs/03-plan-eng-review.md`, `DESIGN.md`.

---

## 0. Project identity

- **Name**: `jimeng-saas` (internal), **即梦创意工作站** (user-facing)
- **Code root**: `G:/AI/jimeng-saas/`
- **Repo**: private for now (init later)
- **Python**: same interpreter as AI 账号管理系统 = `C:\Program Files\Python310\python.exe` (3.10.8)
- **First milestone**: end of Week 1 → can register, log in, fire a single image-generation job, see it complete, view it in library.

---

## 1. File layout (canonical)

```
G:/AI/jimeng-saas/
├── README.md
├── requirements.txt
├── run.bat                              # Windows launcher
├── .env.example                         # Documents all env vars
├── docker-compose.yml                   # prod: app + worker + redis + postgres
├── Dockerfile
├── DESIGN.md                            # ✅ exists
├── AGENTS.md                            # Skill routing + design discipline
├── docs/                                # ✅ design docs live here
│   ├── 01-office-hours.md
│   ├── 02-plan-ceo-review.md
│   ├── 03-plan-eng-review.md
│   ├── design-preview.html
│   └── SPEC.md                          # this file
│
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app + route registration
│   ├── config.py                        # pydantic-settings: reads env
│   ├── database.py                      # engine, get_session(), init_db()
│   ├── security.py                      # Fernet encrypt/decrypt (sessionids)
│   ├── auth.py                          # JWT issue/verify, require_user dep
│   │
│   ├── models/                          # SQLModel tables (one per file)
│   │   ├── __init__.py                  # re-exports all
│   │   ├── user.py                      # User, QuotaEvent, ApiKey
│   │   ├── credential.py                # ProviderCredential (sessionid pool)
│   │   ├── job.py                       # GenerationJob
│   │   ├── artifact.py                  # Artifact, ArtifactFolder, ArtifactTag
│   │   ├── folder.py                    # Folder
│   │   ├── tag.py                       # Tag
│   │   ├── template.py                  # Template (v1.5)
│   │   └── audit.py                     # AuditLog
│   │
│   ├── schemas/                         # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── auth.py                      # RegisterIn, LoginIn, TokenOut
│   │   ├── job.py                       # JobCreateIn, JobOut, JobBatchIn
│   │   ├── artifact.py                  # ArtifactOut, ArtifactUpdateIn
│   │   └── common.py                    # PaginatedOut[T], ErrorOut
│   │
│   ├── routes/                          # FastAPI routers (one per domain)
│   │   ├── __init__.py
│   │   ├── auth.py                      # /api/auth/* + /login, /register pages
│   │   ├── jobs.py                      # /api/jobs/*
│   │   ├── artifacts.py                 # /api/artifacts/*
│   │   ├── folders.py                   # /api/folders/*
│   │   ├── tags.py                      # /api/tags/*
│   │   ├── templates.py                 # /api/templates/* (v1.5)
│   │   ├── billing.py                   # /api/billing/* + /billing page
│   │   ├── pages.py                     # Jinja2: /, /generate, /library, /library/{id}, /settings
│   │   └── admin.py                     # /admin/* (credential management)
│   │
│   ├── providers/                       # Provider abstraction
│   │   ├── __init__.py
│   │   ├── base.py                      # GenerationProvider ABC + dataclasses
│   │   ├── jimeng.py                    # JimengProvider impl (sessionid pool)
│   │   └── registry.py                  # get_provider(name) -> Provider
│   │
│   ├── worker/                          # RQ background jobs
│   │   ├── __init__.py
│   │   ├── connection.py                # redis connection + queue
│   │   ├── jobs.py                      # run_image_gen, run_video_gen
│   │   └── tasks.py                     # enqueue helpers
│   │
│   ├── services/                        # business logic (stateless)
│   │   ├── __init__.py
│   │   ├── quota.py                     # check_and_debit(user, cost) -> bool
│   │   ├── pool.py                      # acquire_credential(provider) -> Credential
│   │   ├── storage.py                   # Storage ABC + LocalStorage + S3Storage
│   │   └── sse.py                       # SSE event bus (per-user channel)
│   │
│   ├── templates/                       # Jinja2 HTML
│   │   ├── base.html                    # nav + {% block content %} (dark Studio theme)
│   │   ├── auth_base.html               # standalone for /login, /register
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html               # /
│   │   ├── generate.html                # /generate (HTMX island)
│   │   ├── library.html                 # /library (gallery grid)
│   │   ├── artifact_detail.html         # /library/{id}
│   │   ├── billing.html
│   │   ├── settings.html
│   │   └── admin/
│   │       ├── credentials.html         # sessionid pool dashboard
│   │       └── jobs.html                # all jobs (ops view)
│   │
│   └── static/
│       ├── style.css                    # Studio Dark theme (from DESIGN.md tokens)
│       ├── app.js                       # HTMX + Alpine + SSE wiring (~200 lines)
│       └── vendor/
│           ├── htmx.min.js              # 14kb gz
│           └── alpine.min.js            # 10kb gz
│
├── data/                                # gitignored
│   ├── artifacts/{user_id}/...          # local storage backend
│   ├── jimeng.db                        # SQLite (dev only)
│   └── uploads/                         # user-uploaded source images (i2i)
│
├── tests/
│   ├── conftest.py                      # pytest fixtures, temp HERMES_HOME-style tmp
│   ├── test_auth.py
│   ├── test_jobs.py
│   ├── test_quota.py
│   ├── test_pool.py
│   ├── test_provider_jimeng.py
│   └── test_api_isolation.py            # multi-tenant WHERE user_id filter
│
└── scripts/
    ├── seed_dev.py                      # dev seed: 1 admin user, 2 test credentials, sample jobs
    └── health_check.py                  # docker-compose readiness probe
```

---

## 2. Environment variables (`.env.example`)

```dotenv
# ─── App ───────────────────────────────────────
JSA_ENV=dev                              # dev | prod
JSA_SECRET_KEY=change-me-in-prod         # JWT signing secret (>= 32 chars)
JSA_MASTER_KEY=change-me-fernet-key      # Fernet master key for sessionid encryption
JSA_BASE_URL=http://localhost:8000       # public base URL (for artifact URLs in dev)

# ─── Database ──────────────────────────────────
# Empty = SQLite at data/jimeng.db; set for PostgreSQL in prod
JSA_DB_URL=

# ─── Redis (RQ worker queue) ───────────────────
JSA_REDIS_URL=redis://localhost:6379/0

# ─── Storage ───────────────────────────────────
JSA_STORAGE_BACKEND=local                # local | s3 | r2
JSA_STORAGE_LOCAL_DIR=data/artifacts
# When backend=s3|r2:
JSA_S3_ENDPOINT=                         # e.g. https://xxx.r2.cloudflarestorage.com
JSA_S3_BUCKET=
JSA_S3_ACCESS_KEY=
JSA_S3_SECRET_KEY=

# ─── Jimeng upstream ───────────────────────────
JSA_JIMENG_UPSTREAM=http://localhost:5100  # the self-hosted jimeng-api Docker service

# ─── Optional: captcha for register ───────────
JSA_TURNSTILE_SITE_KEY=
JSA_TURNSTILE_SECRET=
```

---

## 3. Database schema (complete SQLModel)

### 3.1 `app/models/user.py`

```python
from datetime import datetime, date
from typing import Optional
from sqlmodel import Field, SQLModel

class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    password_hash: str                                   # bcrypt
    name: str = Field(max_length=100)
    plan_tier: str = Field(default="free", max_length=20)  # free | hobby | pro | team
    quota_used: int = Field(default=0)                   # credits used this period
    quota_limit: int = Field(default=10)                 # from plan_tier
    quota_reset_at: datetime                              # next reset
    stripe_customer_id: Optional[str] = Field(default=None, max_length=100)  # v2
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = Field(default=None, index=True)

class QuotaEvent(SQLModel, table=True):
    __tablename__ = "quota_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    event_type: str                                       # image_gen | video_gen | storage | refund
    quantity: int                                         # credits
    cost_credits: int
    job_id: Optional[int] = Field(default=None, foreign_key="generation_jobs.id")
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

class ApiKey(SQLModel, table=True):                     # v1.5 — public API
    __tablename__ = "api_keys"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    key_hash: str = Field(index=True)                    # sha256 of the plaintext key
    name: str = Field(max_length=100)
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 3.2 `app/models/credential.py` (the sessionid pool)

```python
class ProviderCredential(SQLModel, table=True):
    __tablename__ = "provider_credentials"
    id: Optional[int] = Field(default=None, primary_key=True)
    provider_name: str = Field(default="jimeng", max_length=50, index=True)
    region: str = Field(default="cn", max_length=5)      # cn | us | hk | jp | sg
    sessionid_enc: str                                   # Fernet ciphertext
    status: str = Field(default="healthy", index=True)   # healthy | exhausted | banned | cooldown
    last_health_at: Optional[datetime] = None
    daily_calls: int = Field(default=0)
    daily_calls_reset_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 3.3 `app/models/job.py`

```python
class GenerationJob(SQLModel, table=True):
    __tablename__ = "generation_jobs"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    provider_name: str = Field(default="jimeng")
    job_type: str                                        # image | video
    status: str = Field(default="queued", index=True)    # queued | running | succeeded | failed | cancelled
    prompt: str                                          # the text prompt
    params_json: str                                     # JSON: model, ratio, resolution, negative_prompt, etc.
    parent_job_id: Optional[int] = Field(default=None, foreign_key="generation_jobs.id", index=True)  # variation tree
    credential_id_used: Optional[int] = Field(default=None, foreign_key="provider_credentials.id")
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    variation_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 3.4 `app/models/artifact.py`

```python
class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: Optional[int] = Field(default=None, foreign_key="generation_jobs.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str                                            # image | video
    storage_url: str                                     # own storage path/URL
    source_url: Optional[str] = None                     # upstream byteimg.com URL (debug)
    width: Optional[int] = None
    height: Optional[int] = None
    duration_secs: Optional[float] = None                # video only
    bytes_size: Optional[int] = None
    thumbnail_url: Optional[str] = None
    content_hash: Optional[str] = Field(default=None, index=True)  # sha256 dedup
    title: Optional[str] = None                          # user-editable
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    deleted_at: Optional[datetime] = Field(default=None, index=True)

# Many-to-many: artifact ↔ folder
class ArtifactFolder(SQLModel, table=True):
    __tablename__ = "artifacts_folders"
    artifact_id: int = Field(foreign_key="artifacts.id", primary_key=True)
    folder_id: int = Field(foreign_key="folders.id", primary_key=True)
    added_at: datetime = Field(default_factory=datetime.utcnow)

# Many-to-many: artifact ↔ tag
class ArtifactTag(SQLModel, table=True):
    __tablename__ = "artifacts_tags"
    artifact_id: int = Field(foreign_key="artifacts.id", primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", primary_key=True)
```

### 3.5 `app/models/folder.py` + `tag.py`

```python
class Folder(SQLModel, table=True):
    __tablename__ = "folders"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)
    parent_id: Optional[int] = Field(default=None, foreign_key="folders.id")  # nesting
    color: Optional[str] = Field(default=None, max_length=20)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Tag(SQLModel, table=True):
    __tablename__ = "tags"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=50)
    color: Optional[str] = Field(default=None, max_length=20)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 3.6 `app/models/template.py` (v1.5 — schema now, UI later)

```python
class Template(SQLModel, table=True):
    __tablename__ = "templates"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)
    provider_name: str = Field(default="jimeng")
    model: str
    ratio: Optional[str] = None
    resolution: Optional[str] = None
    negative_prompt: Optional[str] = None
    style_prefix: Optional[str] = None
    output_folder_id: Optional[int] = Field(default=None, foreign_key="folders.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None
```

### 3.7 `app/models/audit.py`

```python
class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    action: str                                          # e.g. "credential.access", "user.login", "billing.change"
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
```

---

## 4. API surface (all endpoints)

### 4.1 Auth (`app/routes/auth.py`)

| Method | Path | Body / Params | Response | Notes |
|---|---|---|---|---|
| POST | `/api/auth/register` | `{email, password, name}` + Turnstile token | `201 {token, user}` | rate-limit 5/hr/IP |
| POST | `/api/auth/login` | `{email, password}` | `200 {token, user}` | sets refresh cookie |
| POST | `/api/auth/refresh` | refresh cookie | `200 {token}` | rotates refresh |
| POST | `/api/auth/logout` | — | `204` | clears cookie |
| GET | `/api/me` | — | `200 {user}` | current user |

Pages: `GET /login`, `GET /register` (standalone Jinja2).

### 4.2 Jobs (`app/routes/jobs.py`)

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/jobs` | `JobCreateIn` (below) or `JobBatchIn` | `202 [{job_id, status}]` |
| GET | `/api/jobs` | `?status=&type=&page=&page_size=` | `200 PaginatedOut[JobOut]` |
| GET | `/api/jobs/{id}` | — | `200 JobOut` (with artifacts) |
| POST | `/api/jobs/{id}/cancel` | — | `200` |
| POST | `/api/jobs/{id}/iterate` | `{modify_prompt?, params_override?}` | `202 {job_id}` (child job) |
| GET | `/api/jobs/stream` | SSE | `text/event-stream` — pushes `job.update` events for current user |

```python
class JobCreateIn(BaseModel):
    type: Literal["image", "video"]
    prompt: str
    provider: str = "jimeng"
    params: ImageGenParams | VideoGenParams  # discriminated union
    parent_job_id: int | None = None

class JobBatchIn(BaseModel):
    """Batch: same params, N prompts."""
    type: Literal["image", "video"]
    prompts: list[str]
    provider: str = "jimeng"
    params: ImageGenParams | VideoGenParams

class ImageGenParams(BaseModel):
    model: str = "jimeng-4.0"
    ratio: Literal["1:1","4:3","3:4","16:9","9:16","3:2","2:3","21:9"] = "1:1"
    resolution: Literal["1k","2k","4k"] = "2k"
    negative_prompt: str | None = None
    sample_strength: float | None = None
    intelligent_ratio: bool = False
    source_image_urls: list[str] | None = None  # image-to-image

class VideoGenParams(BaseModel):
    model: str = "jimeng-video-3.5-pro"
    ratio: Literal["1:1","4:3","3:4","16:9","9:16","21:9"] = "1:1"
    resolution: Literal["720p","1080p"] = "720p"
    duration: int = 5
    first_frame_url: str | None = None
    last_frame_url: str | None = None
    function_mode: Literal["first_last_frames","omni_reference"] = "first_last_frames"

class JobOut(BaseModel):
    id: int
    type: str
    status: str
    prompt: str
    params: dict
    parent_job_id: int | None
    variation_count: int
    error_message: str | None
    artifacts: list[ArtifactOut] = []
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
```

### 4.3 Artifacts (`app/routes/artifacts.py`)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| GET | `/api/artifacts` | `?folder=&tag=&q=&kind=&page=&page_size=` | `PaginatedOut[ArtifactOut]` |
| GET | `/api/artifacts/{id}` | — | `ArtifactOut` |
| PATCH | `/api/artifacts/{id}` | `{title?, folder_ids?, tag_ids?}` | `ArtifactOut` |
| DELETE | `/api/artifacts/{id}` | — | `204` (soft) |
| GET | `/api/artifacts/{id}/download` | `?size=full\|thumb` | `302` to signed storage URL |
| POST | `/api/artifacts/batch-export` | `{ids: [], rename_pattern: str}` | `200 application/zip` |

### 4.4 Folders / Tags

Standard CRUD: `GET/POST/PATCH/DELETE /api/folders`, `/api/tags`. All user-scoped.

### 4.5 Billing (`app/routes/billing.py`)

| Method | Path | Response |
|---|---|---|
| GET | `/api/billing/usage` | `{plan, quota_used, quota_limit, quota_reset_at, history: [QuotaEventOut]}` |
| GET | `/billing` | Jinja2 page |
| POST | `/api/billing/checkout` | v2: Stripe checkout session URL |

### 4.6 Admin (`app/routes/admin.py`, `is_admin=True` required)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/admin/credentials` | — | Jinja2 dashboard (pool health) |
| POST | `/api/admin/credentials` | `{provider, region, sessionid, notes}` | `201` (encrypts sessionid) |
| POST | `/api/admin/credentials/{id}/health-check` | — | `200 {status}` |
| DELETE | `/api/admin/credentials/{id}` | — | `204` |
| GET | `/admin/jobs` | — | Jinja2 (all jobs all users) |

### 4.7 Pages (`app/routes/pages.py`, Jinja2)

| Path | Template | Notes |
|---|---|---|
| `/` | `dashboard.html` | recent jobs, quota, quick-action |
| `/generate` | `generate.html` | HTMX/Alpine island: prompt textarea, batch, params rail, live SSE grid |
| `/library` | `library.html` | gallery grid + folder sidebar + filter bar (HTMX swap) |
| `/library/{id}` | `artifact_detail.html` | image + prompt + params + variation tree + tag edit (Alpine) |
| `/folders/{id}` | `library.html` (filtered) | reuse |
| `/templates` | (v1.5) | |
| `/billing` | `billing.html` | |
| `/settings` | `settings.html` | profile, password, API keys (v1.5) |

---

## 5. Provider abstraction

### 5.1 `app/providers/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

@dataclass
class ProviderHealth:
    healthy: bool
    remaining_quota: int | None = None  # None if unknown
    message: str = ""

@dataclass
class GeneratedArtifact:
    source_url: str                      # upstream URL (will be downloaded)
    width: int | None = None
    height: int | None = None
    duration_secs: float | None = None

class GenerationProvider(ABC):
    name: str = ""

    @abstractmethod
    async def health_check(self, credential) -> ProviderHealth: ...

    @abstractmethod
    async def generate_images(self, prompt: str, params: dict, credential) -> list[GeneratedArtifact]: ...

    @abstractmethod
    async def generate_videos(self, prompt: str, params: dict, credential) -> list[GeneratedArtifact]: ...

    @abstractmethod
    def supported_models(self) -> list[dict]: ...
```

### 5.2 `app/providers/jimeng.py`

Implements `GenerationProvider` by calling the self-hosted jimeng-api Docker service at `JSA_JIMENG_UPSTREAM` (default `http://localhost:5100`). Calls:

- `POST /v1/images/generations` (text-to-image)
- `POST /v1/images/compositions` (image-to-image)
- `POST /v1/videos/generations` (text/image-to-video)

Auth: `Authorization: Bearer {region_prefix}{sessionid}` where region_prefix is `""` for cn, `"us-"`/`"hk-"`/`"jp-"`/`"sg-"` for international. Timeout 300s. Returns the parsed `GeneratedArtifact` list; download is done by the worker.

### 5.3 `app/providers/registry.py`

```python
_PROVIDERS = {"jimeng": JimengProvider}
def get_provider(name: str) -> GenerationProvider:
    return _PROVIDERS[name]()
```

---

## 6. Worker pipeline

### 6.1 `app/worker/connection.py`

```python
from redis import Redis
from rq import Queue
import os
redis = Redis.from_url(os.environ["JSA_REDIS_URL"])
queue = Queue("jimeng", connection=redis)
```

### 6.2 `app/worker/jobs.py`

```python
def run_image_job(job_id: int):
    """RQ entry point. Loads job from DB, runs provider, saves artifacts."""
    with get_session_scope() as session:
        job = session.get(GenerationJob, job_id)
        try:
            job.status = "running"; job.started_at = utcnow()
            credential = pool.acquire(session, provider="jimeng")  # health-checks
            provider = get_provider(job.provider_name)
            artifacts = provider.generate_images(job.prompt, json.loads(job.params_json), credential)
            for a in artifacts:
                local_url = storage.download_and_store(a.source_url, user_id=job.user_id)
                session.add(Artifact(job_id=job.id, user_id=job.user_id, kind="image",
                                     storage_url=local_url, source_url=a.source_url,
                                     width=a.width, height=a.height))
                # also generate thumbnail
            job.status = "succeeded"; job.completed_at = utcnow()
            job.variation_count = len(artifacts)
            quota.debit(session, job.user_id, cost=1, job_id=job.id)  # success only
            sse.publish(job.user_id, "job.update", JobOut.from_orm(job).dict())
        except CredentialExhausted:
            job.status = "failed"; job.error_message = "All sessionids exhausted"
            sse.publish(job.user_id, "job.update", {"id": job.id, "status": "failed"})
        except Exception as e:
            job.status = "failed"; job.error_message = str(e)
            sse.publish(job.user_id, "job.update", {"id": job.id, "status": "failed"})
```

### 6.3 Worker process

`worker.bat`:
```bat
"C:\Program Files\Python310\python.exe" -m rq worker jimeng --url redis://localhost:6379/0
```

Docker: separate `worker` service in `docker-compose.yml` running the same.

---

## 7. Services

### 7.1 `app/services/pool.py`

```python
def acquire(session, provider: str = "jimeng") -> ProviderCredential:
    """Pick a healthy credential, rate-limit aware. Raises if all exhausted."""
    # SELECT * FROM provider_credentials
    # WHERE provider_name=? AND status='healthy'
    # ORDER BY daily_calls ASC, last_health_at DESC
    # LIMIT 1
    # If none: raise CredentialExhausted
```

### 7.2 `app/services/storage.py`

```python
class Storage(ABC):
    @abstractmethod
    def download_and_store(self, source_url: str, user_id: int, ext: str = "png") -> str: ...
    @abstractmethod
    def signed_url(self, storage_url: str, expires: int = 3600) -> str: ...

class LocalStorage(Storage):
    # saves to data/artifacts/{user_id}/{yyyy}/{mm}/{ulid}.{ext}
    # signed_url returns a time-limited /api/storage/{token} URL

class S3Storage(Storage):
    # uses boto3 / cloudflare-r2 client
```

### 7.3 `app/services/quota.py`

```python
def check_and_debit(session, user_id: int, cost: int, job_id: int | None) -> bool:
    """Atomically check + debit. Uses advisory lock on user_id to prevent races."""
    # pg_advisory_xact_lock(user_id) on PostgreSQL; SELECT ... FOR UPDATE on SQLite
    user = session.get(User, user_id)
    if user.quota_used + cost > user.quota_limit:
        return False
    user.quota_used += cost
    session.add(QuotaEvent(user_id=user_id, event_type="image_gen" if cost else "refund",
                           quantity=1, cost_credits=cost, job_id=job_id))
    return True
```

### 7.4 `app/services/sse.py`

Per-user channel via Redis pub/sub or in-process asyncio queue (dev). Worker publishes; SSE endpoint subscribes.

---

## 8. Auth (`app/auth.py`)

```python
# JWT: HS256, access 15min, refresh 30d (rotated on use)
# Access token in Authorization: Bearer <token>
# Refresh token in http-only SameSite=Strict cookie "jsa_refresh"
# Password hashing: passlib[bcrypt]

def hash_password(p): return pwd_context.hash(p)
def verify_password(p, h): return pwd_context.verify(p, h)
def create_access_token(user_id): ...  # jwt.encode, exp=15min
def create_refresh_token(user_id): ...
def require_user(request, session) -> User:  # FastAPI dependency
    # parse Authorization header, verify JWT, load user, 401 if invalid
```

---

## 9. Security (`app/security.py`)

```python
from cryptography.fernet import Fernet
_fernet = Fernet(os.environ["JSA_MASTER_KEY"].encode())
def encrypt(value: str) -> str: return _fernet.encrypt(value.encode()).decode()
def decrypt(token: str) -> str: return _fernet.decrypt(token.encode()).decode()
```

Used only for `provider_credentials.sessionid_enc`.

---

## 10. requirements.txt

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
sqlmodel>=0.0.16
jinja2>=3.1.3
python-multipart>=0.0.9
cryptography>=42.0.0
itsdangerous>=2.1.2
psycopg2-binary>=2.9.0          # PostgreSQL (prod)
pydantic-settings>=2.0.0
passlib[bcrypt]>=1.7.4          # passwords
python-jose[cryptography]>=3.3  # JWT
redis>=5.0.0                    # RQ
rq>=1.16.0
httpx>=0.27.0                   # call jimeng-api (async)
slowapi>=0.1.9                  # rate limiting
pillow>=10.0.0                  # thumbnail generation
boto3>=1.34.0                   # S3/R2 storage (optional)
```

---

## 11. Build order (week-by-week)

### Week 1 — Walks and talks (MVP vertical slice)
1. Init project: `requirements.txt`, `run.bat`, `app/__init__.py`, `config.py`, `database.py`.
2. All `models/*.py` (per §3). Run `init_db()` to create tables.
3. `security.py` (Fernet) + `auth.py` (JWT, bcrypt).
4. `routes/auth.py` + `templates/login.html` + `register.html` (standalone, Studio dark).
5. `routes/pages.py` minimal: `/` dashboard stub, `/generate` stub, `/library` stub.
6. `templates/base.html` + `static/style.css` (port DESIGN.md tokens verbatim — Pitfall #21 of python-web-crud-app).
7. `providers/base.py` + `providers/jimeng.py` + `providers/registry.py`.
8. `worker/connection.py` + `worker/jobs.py` (image only).
9. `services/pool.py` + `services/storage.py` (Local only) + `services/quota.py`.
10. `routes/jobs.py` POST `/api/jobs` (single image) + SSE stream.
11. Seed dev: 1 admin, 1 sessionid credential.
12. **End of week-1 acceptance**: register → log in → POST a single image-gen job → see it queue, run, succeed → appear in `/library`.

### Week 2 — Product feels real
13. Batch prompt entry (textarea, one per line) + CSV upload (`POST /api/jobs` with `prompts: list[str]`).
14. Library grid with folder sidebar + tag filter + search (HTMX).
15. Artifact detail page + variation tree (POST `/api/jobs/{id}/iterate`).
16. `routes/admin.py` + admin credentials dashboard.
17. Quota enforcement + `quota_events` audit.
18. Soft-delete + recycle bin for artifacts.

### Week 3 — Polish + video
19. `/generate` canvas polish: live SSE result grid, image-reveal animation, progress bars.
20. Video generation (`/v1/videos/generations`): new job_type, longer timeout, different UI affordance.
21. Template engine (v1.5) — schema already exists.
22. Rate limiting (slowapi) + Turnstile captcha on register.
23. PostgreSQL migration testing (dual-engine via `JSA_DB_URL`).
24. `docker-compose.yml` + Dockerfile + health checks.

### Week 4 — Billable
25. Stripe integration (checkout session + webhook).
26. Plan tier enforcement + quota reset cron.
27. Public API + API keys (v1.5).
28. S3/R2 storage backend.
29. Audit log review page (admin).
30. Production deploy + monitoring.

---

## 12. Acceptance tests (must pass before "v1 shipped")

- `tests/test_auth.py`: register, login, refresh, logout, unauthorized 401.
- `tests/test_jobs.py`: enqueue image job → worker runs → artifact created → quota debited.
- `tests/test_quota.py`: insufficient credits → 402, race condition with N concurrent requests → exactly one succeeds.
- `tests/test_pool.py`: all credentials exhausted → `CredentialExhausted` raised → job failed status.
- `tests/test_provider_jimeng.py`: mocked upstream — happy path, 401 (expired sessionid), 500, timeout.
- `tests/test_api_isolation.py`: user A cannot see user B's artifacts (404), cannot PATCH them, cannot download.
- E2E (manual `curl` + browser): full register → batch → library → iterate flow.

---

## 13. Open questions (resolve before Week 1 day 1)

1. **Where does the jimeng-api Docker service run?** Same machine (port 5100)? Separate?
2. **How many sessionids do you have to seed the pool?** This sets initial capacity.
3. **Do you already have a Stripe account?** Affects Week 4 vs defer.
4. **Domain name?** For JWT issuer, CORS, Stripe redirect.
5. **S3/R2 credentials ready?** Can start with local FS, but confirm.
6. **PostgreSQL: local install or managed (Supabase/Neon/RDS)?**

---

## 14. AGENTS.md (skill routing + design discipline)

```markdown
# Jimeng SaaS — Agent Guide

## Skill routing
- Product decisions / scope → re-read docs/02-plan-ceo-review.md
- Architecture questions → docs/03-plan-eng-review.md
- Any UI/visual choice → DESIGN.md is source of truth, do not deviate
- Bug investigation → /investigate
- Pre-commit review → /review
- Visual QA → /qa on http://localhost:8000
- Ship PR → /ship

## Hard rules
- Every DB query that touches user-scoped tables MUST filter by user_id.
- Never log sessionids (even encrypted). Use [REDACTED] in logs.
- Every new field added to a model → update schema, routes, templates, export in one pass.
- CSS variable names MUST match DESIGN.md exactly (no `--card`, use `--bg-elevated`).
- Generation is async — never block HTTP on provider calls.
- Failed jobs don't debit quota. Ever.
```
