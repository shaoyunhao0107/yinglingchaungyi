# /plan-ceo-review — Jimeng SaaS

> Mode: **SCOPE EXPANSION** — find the 10-star product, challenge premises,
> expand scope where it creates a better product.
> Input: `docs/01-office-hours.md`.
> **Status**: v1 — ready for `/plan-eng-review`.

---

## Premise challenges (what we're taking on faith, and shouldn't)

### Challenge 1: "MVP is just batch文生图 + library"

**The premise is too small.** A batch文生图 tool is a feature, not a product.
A competitor (or即梦官方 themselves) ships batch in a weekend update and we're
dead. The wedge must be **a workflow platform**, not a batch endpoint.

**Reframe**: MVP is **"the home base for a Chinese content creator's AI image
workflow"** — batch is the entry hook, but the product is everything that
happens after generation: organize, re-iterate, template, publish.

### Challenge 2: "即梦-only for v1"

This is correct for v1 (don't boil the ocean), but the **positioning** must
already be "multi-provider ready". The architecture should treat即梦 as a
pluggable provider, not a hardcoded one. If即梦 kills us tomorrow, we swap to
Midjourney/SD without rewriting the product.

### Challenge 3: "Tech stack = FastAPI + Jinja2"

Jinja2 server-rendered is fine for the **dashboard/library/billing** parts
(they're forms + tables, server-rendered is correct). But the **generation
canvas** (batch prompt entry, live progress, image grid with selection) is
highly interactive — that part should be a thin React/HTMX island, not a
full Jinja2 page reload on every interaction.

**Reframe**: hybrid rendering. Jinja2 for the chrome, interactive islands
for the workspace. Don't pick one — use both where each wins.

### Challenge 4: "sessionid as the unit of credential"

The user said "backend fills sessionid". That's correct for v1 ops, but for
**SCOPE EXPANSION** we must think bigger: **sessionid pool with health
monitoring + automatic rotation + alerting** is the invisible infra that
makes the SaaS reliable. A single sessionid is a single point of failure.
A pool with N sessionids + health checks + per-sessionid rate-limit +
graceful degradation when one dies — that's the moat no individual user
can replicate.

---

## The 10-star product (what would make this genuinely great)

A 5-star product = "即梦 batch + library, works." Forgettable.

A **10-star product** = this:

### The "Creator Home Base" vision

> A content creator opens the SaaS every morning the way a developer opens
> their IDE. It's where their **visual asset universe** lives: every image
> they ever generated, every prompt that worked, every template they
> reusable, every project they're iterating on. They can fire a batch before
> breakfast, review yesterday's output with coffee, spin a video variant of
> the best one, drop it into a公众号-sized template, and export the whole
> batch renamed and formatted — all without leaving the workspace.

The 10-star moments:

1. **"Coffee-time review"**: wake up, last night's batch is done, presented
   as a "good morning, here are your 24 variations, we pre-tagged the 6 best
   by prompt-match score" — *not* "here's a grid, sort yourself".

2. **"One-click re-iterate"**: hover any image → "give me 4 more like this
   but with X changed" → done in 30s. No re-entering the prompt. The
   original prompt + params are *attached to the image*, forever.

3. **"Template engine"**: define a "公众号封面" template (16:9, 2k, specific
   negative prompt, specific style prefix) → one click per article. The
   template library is **the user's accumulated taste** — that's what they
   pay for, that's what keeps them.

4. **"Batch from CSV"**: paste a list of article titles → auto-generate
   prompts → batch-fire. Walk away. The whole month's配图 done in one sitting.

5. **"Asset publish pipeline"**: pick 6 images → "export as公众号 batch
   (renamed 公众号-标题-01.png ... )" → drop into Obsidian vault / 公众号
   backend directly. No manual renaming, no manual upload to a separate
   editor.

6. **"Video variant of any image"**: any image in library → "make this
   a 5s video" → one click. The image-to-video path is the killer feature
   for短视频运营, and we already have the image.

### What "10-star" means for scope

These are NOT v1 scope, but they're the **north star**. Every v1 decision
must not preclude them:

- v1 ships batch + library + persistent prompt-attached-to-image.
- v1.5 ships templates + video.
- v2 ships "smart review" + publish pipeline.
- v2.5 ships team workspaces.
- v3 ships automation / API.

---

## Scope expansion picks (cherry-pick into v1 / v1.5)

From the SCOPE EXPANSION pass, these additions make v1 strictly better
without exploding scope:

### Pick into v1 (high leverage, low cost)

1. **Prompt attached to every image, forever** (not just "history list").
   Every image is a first-class object: prompt + params + model + timestamp
   + tags + folder + variations. Cost: ~0 (DB schema). Value: huge.

2. **Variation tree** ("re-iterate on image X" creates a child of X).
   Cost: a `parent_id` column. Value: this is the "I'm iterating" moment
   that the official UI completely lacks.

3. **Folder + tag + smart-filter library**. Cost: 2 join tables. Value:
   this is the "asset management" the target users绝望 about.

4. **CSV batch upload**. Cost: 1 endpoint + 1 file input. Value: this is
   the wedge that beats babysitting the official UI.

### Defer to v1.5 (high value, but blocks v1 ship)

- **Video generation** (different latency budget, different UX — needs its
  own progress UX, ~minutes not ~seconds).
- **Template engine** (powerful, but only after users have generated
  enough to know what to template).
- **"Smart review" pre-tagging** (needs ML, not v1).

### Defer to v2+

- Team workspaces.
- Multi-provider (即梦 only for v1).
- Public API / integrations.

---

## Risks, revisited under SCOPE EXPANSION

| Risk | v1 mitigation | North-star mitigation |
|---|---|---|
| **Legal / ToS** | Position as "workflow tool", ToS disclaims reselling access, private beta first. | Get an official即梦 API partnership once we have user count to leverage. |
| **sessionid supply** | Pool of N with health checks + manual replenishment. | Build automated replenishment (paid workers, CAPTCHA solver, etc.) — this IS the moat. |
| **Upstream changes break us** | Self-researched backend (decided), weekly upstream sync. | Multi-provider abstraction (v2.5) means we survive any single provider dying. |
| **官方 launches workflow features** | Be faster + more focused. | Distribution + accumulated user templates/library = switching cost. |
| **Pricing mismatch** | ¥29–99/mo for creators (well below MJ ¥100+ but with中文 workflow). | Tiered by usage; team plans at ¥299+/mo. |

---

## Locked decisions for v1 (after this review)

| Decision | Locked value | Changed from office-hours? |
|---|---|---|
| v1 scope | **文生图 + 图生图 batch + persistent library + folders/tags + CSV batch + variation tree** | YES — expanded from "just batch + history" |
| Architecture | **Provider-abstracted from day 1** (即梦 is plugin, not hardcoded) | YES — was即梦-hardcoded |
| Rendering | **Hybrid: Jinja2 for chrome, interactive island for workspace canvas** | YES — was pure Jinja2 |
| Backend | **Self-hosted即梦 service with sessionid pool + health check + rotation** | YES — was single sessionid |
| Pricing | **¥29/mo (hobby), ¥99/mo (pro), ¥299+/mo (team)** | NEW |
| v1.5 (queued) | Video generation, template engine | NEW |
| v2+ (queued) | Smart review, publish pipeline, team workspaces, multi-provider, API | NEW |

---

## Output to `/plan-eng-review`

The engineering review must lock:

1. **DB schema** for: users, sessionid pool, generation jobs, image assets,
   folders, tags, variation trees, templates (v1.5 placeholder).
2. **Service architecture**: FastAPI app + background worker (Celery/RQ) +
   sessionid pool manager + object storage adapter.
3. **Provider abstraction**: `GenerationProvider` interface, JimengProvider impl.
4. **Async job model**: image gen is 10–60s, must be background-polled, not
   blocking HTTP. Define the job lifecycle + websocket/SSE push.
5. **Hybrid rendering plan**: which pages are Jinja2, which are interactive
   islands, what's the JS payload budget.
6. **Security model**: how sessionids are stored (encrypted), how user auth
   works (JWT? session cookies?), how uploads are sandboxed.
