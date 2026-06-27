# Office Hours — Jimeng SaaS

> YC office hours for the product, run through gstack's `/office-hours` methodology.
> Six forcing questions answered from the user's clarify responses + market analysis.
> **Status**: DRAFT v1 — ready for `/plan-ceo-review`.

---

## One-liner

**A paid SaaS that gives Chinese content creators (公众号作者、设计师、电商运营) a fast batch AI image/video generation workspace with persistent history and asset library — powered by self-hosted Jimeng API, hiding all the sessionid / Docker / reverse-engineering pain behind a clean web UI.**

---

## The six forcing questions

### 1. Demand reality — who is desperate enough to pay?

**Target**: Chinese content creators who批量产图 but are blocked by the official Jimeng/Dreamina web UI:

- **公众号作者**: each article needs 4–8 配图, currently they flip between即梦官网 and their editor, manually downloading, renaming, filing. Every article = 30+ minutes of grunt work.
- **电商运营**: need dozens of product hero shots / lifestyle images per SKU launch, in consistent aspect ratios (16:9 主图, 1:1 详情, 9:16 短视频封面).
- **设计师**: exploring variations rapidly — the official UI's lack of history/iteration makes it useless as a working tool.

**Why they'd pay**:
- Official UI is free but **lacks batch, history, asset library, team workflow**.
- Midjourney is ¥100+/mo, English-only, Discord-based (Chinese users hate it).
- This SaaS fills the "I just want to generate 20 versions, save them, come back tomorrow and pick" gap that no current product solves well for Chinese users.

**What they will NOT pay for**: another raw API. They pay for the **workflow**.

### 2. Status quo — what do they do today?

| User | Current workflow | Pain |
|---|---|---|
| 公众号作者 | Open jimeng.jianving.com → prompt → wait → right-click save → rename → upload to editor. Repeat 8× per article. | No batch. No history. Lose track of which prompt made which image. Re-doing work constantly. |
| 电商运营 | Same, but also needs to resize/reformat for each channel. Often outsourced to a junior who burns a day per launch. | Slow. Junior expensive. Iteration painful. |
| 设计师 | Use Midjourney (English, Discord) or jimeng web. Save to local folders named by date. | No proper asset management. Can't easily re-iterate on a saved image. |

**The wedge**: a workspace that treats generation as a **first-class persistent object** (prompt + params + outputs + tags + folder), not a one-shot command. None of the现状 players do this well.

### 3. Desperate specificity — the exact moment of pain

> "I'm publishing a公众号 article, I need 6 配图 in 16:9, I have the prompts ready, I want to fire them all off, walk away for 5 minutes, come back and have all 24 variations (4 per prompt × 6 prompts) ready to pick from, already saved to my library with the prompts attached so I can find them next week."

That **walk-away-and-come-back-to-everything-ready** with persistent history is the绝望 moment. The official UI makes you babysit each generation.

### 4. Narrowest wedge — what's the smallest thing that wins?

**MVP = "batch text-to-image workspace with persistent library"**:

1. Paste N prompts (one per line, or upload a CSV).
2. Pick model + ratio + resolution once (applies to all).
3. Click "Generate all".
4. Walk away. Come back. All done, in your library.
5. Filter, tag, download, re-iterate.

**Explicitly out of MVP** (don't build v1):
- Video generation (add in v1.5 — same backend, different latency budget).
- Team collaboration (v2).
- Public API / integrations (v2).
- Multiple AI providers (即梦-only for v1, don't boil the ocean).

### 5. Observation — what's the observable signal that this is right?

**Pre-build signals already observed**:
- jimeng-api GitHub repo: **1k+ stars, 109 commits, active maintenance** — confirms the underlying capability is real and in demand.
- Garry Tan's gstack ships its own `/browse` QA tool — confirms the "headless generation + evidence" pattern is broadly useful.
- User's own existing SaaS (AI 账号管理系统) targets the same buyer persona (managing subscriptions for the same tools) — **adjacent product, same customer**, so they have distribution.
- Competitor scan: 即梦官网 (free, no workflow), Midjourney (paid, English), Stable Diffusion webUIs (self-hosted, technical) — **no one owns the "Chinese-content-creator workflow" position**.

**Validation gate before coding v1**:
- Manual test: hand 5 target users a Figma clickable prototype showing the batch-prompt + walk-away flow. If 3/5 say "I'd pay ¥30-100/mo for this", build v1. If not, iterate on the wedge.

### 6. Future-fit — does this survive 12 months?

**Threats**:
- **官方 opens a real API** — kills the reverse-engineering moat. **Mitigation**: the moat isn't the API, it's the **workflow + library + distribution**. If官方 opens an API, we just swap backends.
- **sessionid gets killed** — mitigation: self-research the backend (decision already made), keep tracking upstream changes, maintain a sessionid pool with rotation.
- **Midjourney localizes for China** — real threat. **Mitigation**: be the best即梦-specific workflow first; Midjourney switching cost (English, Discord habit) keeps Chinese users sticky.

**Where this goes in 12 months**:
- v1: 即梦 image SaaS for Chinese content creators
- v1.5: + 即梦 video
- v2: + team workspaces
- v2.5: + multi-provider (即梦 + Midjourney + SD) — become the "aggregated AI image workflow for Chinese creators"
- v3: + automation (cron batch from templates, API)

---

## Product decisions locked (from clarify)

| Decision | Locked value |
|---|---|
| Form factor | **Web app** (frontend + backend) |
| User model | **External SaaS** — full user system, registration, login, quota, billing |
| Tech stack | **Full-stack Python**: FastAPI + Jinja2 (server-rendered) + lightweight frontend (HTMX or minimal React). Matches user's existing AI 账号管理系统 stack. |
| Target user | 公众号作者 / 设计师 / 电商运营 (Chinese content creators, batch generation + library workflow) |
| Core pain | History + batch generation + asset library management (二次调用素材) |
| Backend | **全自研即梦 API service** (not the official Docker image). Full control over sessionid rotation, retries, rate-limiting. |
| Credential handling | **Backend owns sessionid** — end users never see it. Users get a normal account; the backend maps their requests to a sessionid pool. |

## Open risks to flag in `/plan-ceo-review`

1. **Legal**: reverse-engineered API + paid SaaS = ToS risk. Need a clear positioning (wrapper/tool vs. reselling access).
2. **sessionid supply**: how do we replenish expired sessionids at scale? Manual? Paid workers? This is an ops cost that caps growth.
3. **Cost-per-call**: free tier on即梦 has daily limits; paid tier needed for any serious user volume. Pricing must cover the即梦 paid-tier cost + margin.
4. **Differentiation**: the workflow is the moat, not the tech. v1 must NAIL the batch+library UX, not just work.
