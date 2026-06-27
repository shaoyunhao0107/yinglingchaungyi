# Design System — Jimeng SaaS (即梦创意工作站)

## Product Context

- **What this is:** A paid SaaS that gives Chinese content creators (公众号作者 / 设计师 / 电商运营) a fast batch AI image/video generation workspace with persistent library, folders, tags, and variation trees — powered by self-hosted Jimeng API.
- **Who it's for:** Chinese content creators who批量产图 — they ship articles, product launches, short-video covers. They hate the官方即梦 UI's lack of history/batch/library. They want their "AI image home base".
- **Space/industry:** AI image/video generation tools. Peers: 即梦官网, Midjourney, Stable Diffusion webUIs, Civitai, Krea.
- **Project type:** Web app (dashboard + interactive canvas + asset library). Mostly server-rendered Jinja2 with HTMX/Alpine islands for the generation canvas and library grid.

## Memorable thing

> **"打开它像走进自己的创意工作室，而不像打开一个 AI 工具。"**

Every design decision serves this. The user is a creator, not a prompt engineer. The tool should feel like an extension of their taste, not a panel of sliders.

## Aesthetic Direction

- **Direction:** **Studio Dark** — Linear-derived dark base + a single expressive accent (warm violet/magenta gradient for creative energy). The base is professional and trustworthy (so billing and quota feel safe), the accent is alive (so generation feels creative, not bureaucratic).
- **Decoration level:** **intentional** — restrained UI chrome (so the images/videos pop), but with a single signature flourish: a soft glow/aurora treatment behind hero moments (empty-state, first-generation, success).
- **Mood:** Professional enough for billing, alive enough for creativity. The library page should feel like a gallery wall — the user's work shines, the UI recedes.
- **Reference sites:** Linear (base), Krea.ai (creative dark + accent energy), Civitai (gallery-grid density), Vercel (typographic discipline).

## SAFE vs RISK

**SAFE (category baseline — users expect this):**
- Dark dashboard aesthetic with grayscale base (every creative tool has this now)
- Side navigation with icon + label
- Grid-based image library with hover affordances
- Modal dialogs for generation params
- Status pills for job state

**RISKS (where this product gets its own face):**
1. **Aurora accent** — instead of a flat brand color, the accent is a 2-stop warm gradient (violet→magenta). Used sparingly: primary CTAs, active states, success glow. It evokes ink/photographic developer — a visual metaphor for "creation happening". Most competitors use flat blue or purple.
2. **Gallery-wall library** — the library page treats images as first-class objects on a near-black wall, not as thumbnails in a table. Hover reveals prompt (the "title") and a subtle lift. This is a posture difference: we treat the user's work as art, not as output.
3. **No "generation form"** — generation is a canvas, not a form. The prompt field is huge (it's the most important input), params live in a collapsible right rail (not above the prompt), and results stream in below in real-time. We don't make the user feel like they're filling out a tax form to make art.

## Typography

- **Display/Hero:** **Cabinet Grotesk** (700/800) — geometric, confident, slightly wider than Inter. Reads as "modern creative tool", not "enterprise dashboard". Pairs with the aurora accent without fighting it.
- **Body:** **Plus Jakarta Sans** (400/500/600) — friendly geometric sans, excellent Chinese fallback (works with system PingFang/Source Han). More character than Inter, more readable than Geist at small sizes for mixed CJK/Latin.
- **UI/Labels:** Plus Jakarta Sans (same as body, 500 weight)
- **Data/Tables:** **JetBrains Mono** (with tabular-nums) — for prompt params (model, ratio, resolution), credit usage, timestamps. Reads as "this is a precise spec", not "this is marketing copy".
- **Chinese fallback chain:** PingFang SC → Source Han Sans SC → Microsoft YaHei → sans-serif. Critical for 公众号作者 use case.
- **Loading:** Google Fonts + Bunny Fonts mirror as fallback. Self-host in prod.
- **Scale (modular 1.2):**
  - xs: 12px (0.75rem) — labels, meta
  - sm: 14px (0.875rem) — body small, table rows
  - base: 16px (1rem) — body
  - lg: 19px (1.1875rem) — section headings
  - xl: 23px (1.4375rem) — page titles
  - 2xl: 31px (1.9375rem) — hero numerics
  - 3xl: 45px (2.8125rem) — marketing hero (rare in app)

## Color

- **Approach:** **balanced with expressive accent** — neutrals are restrained (3-tier grayscale), accent is a gradient (used rarely = high impact).

### Dark mode (default)

```
Backgrounds (3-tier luminance, NOT flat black):
  --bg-base:      #0a0a0c   (near-black, slightly cool)
  --bg-elevated:  #131316   (cards, modals)
  --bg-sunken:    #050506   (full-bleed gallery wall — the library)

Text:
  --text-primary:    #f5f5f7   (not pure white)
  --text-secondary:  #c2c7d0
  --text-tertiary:   #7a7f8a   (meta, timestamps)
  --text-quaternary: #4a4d55   (placeholders)

Borders:
  --border-subtle:  rgba(255,255,255,0.06)
  --border-standard: rgba(255,255,255,0.10)
  --border-strong:  rgba(255,255,255,0.18)   (hover/focus)

Accent (THE signature — warm violet→magenta, evokes ink/developer):
  --accent-from:   #8b5cf6   (violet-500)
  --accent-to:     #ec4899   (pink-500)
  --accent-solid:  #a855f7   (violet-500, for solid bg like badges)
  --accent-hover:  #9333ea   (violet-600)
  --accent-glow:   rgba(168,85,247,0.20)   (soft halo behind hero/CTA)

Semantic:
  --success: #10b981   (emerald-500)
  --warning: #f59e0b   (amber-500)
  --error:   #ef4444   (red-500)
  --info:    #3b82f6   (blue-500)
```

### Light mode (for docs/billing, rarely in app)

```
  --bg-base:      #ffffff
  --bg-elevated:  #f7f7f8
  --bg-sunken:    #ededee
  --text-primary: #18181b
  ... (mirror of dark, inverted)
```

**Dark mode is the default** — this is a creative tool, images look better against dark. Light mode exists for printable invoices and the rare user who wants it.

## Spacing

- **Base unit:** 4px (Tailwind-compatible)
- **Density:** **comfortable** (not compact — creators need breathing room; not spacious — we have a lot of content)
- **Scale:**
  ```
  2xs:  2px   (icon-to-label gap)
  xs:   4px   (tight cluster)
  sm:   8px   (form field padding)
  md:   12px  (card internal padding)
  lg:   16px  (standard gap)
  xl:   24px  (section gap)
  2xl:  32px  (page-level vertical rhythm)
  3xl:  48px  (hero spacing)
  4xl:  64px  (marketing only)
  ```

## Layout

- **Approach:** **hybrid** — strict grid for the app shell (nav + content + optional right rail), gallery-asymmetric for the library, centered narrow for auth/billing.
- **App shell:** Fixed left sidebar (220px, collapsible to 64px icon-only) + main content. Sidebar: logo, nav (Dashboard / 生成 / 媒体库 / 文件夹 / 模板(v1.5) / 账单 / 设置), bottom: user avatar + plan badge.
- **Generation canvas:** 3-zone layout — left (prompt + batch list, 40%), center (live results grid, 60%), right (params rail, collapsible, 280px). On narrow screens, right rail becomes a drawer.
- **Library:** full-bleed masonry grid. Sidebar stays. Filter bar above grid (folder breadcrumb, tag chips, search, sort).
- **Max content width:** 1440px (app), 640px (auth/billing narrow)
- **Border radius:**
  ```
  --radius-sm:   6px    (badges, tags, pills)
  --radius-md:   10px   (buttons, inputs)
  --radius-lg:   14px   (cards, modals)
  --radius-xl:   20px   (hero panels, empty states)
  --radius-full: 9999px (avatars, status dots)
  ```

## Motion

- **Approach:** **intentional** — most UI is static (creators don't want their tool wiggling). Motion is reserved for: state transitions (job status changes), entrance reveals (results streaming in), and the signature aurora glow (hero moments).
- **Easing:**
  - enter: `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-quint — decelerating, "settling")
  - exit: `cubic-bezier(0.7, 0, 0.84, 0)` (ease-in-quint)
  - move: `cubic-bezier(0.4, 0, 0.2, 1)` (ease-in-out-quint)
- **Duration:**
  - micro: 80ms (hover states, button press)
  - short: 180ms (dropdowns, toasts)
  - medium: 320ms (modal open, panel slide)
  - long: 480ms (result-card entrance with subtle scale + fade)
- **Signature animations:**
  - **Aurora glow**: behind the "Generate" CTA when idle, behind the first result card when it arrives. A slow (8s) radial-gradient shift, low opacity (0.2). Evokes "the machine is thinking / creation is happening".
  - **Image reveal**: each new image enters with `opacity 0→1 + scale 0.96→1` over 480ms ease-out-quint, staggered 60ms between cards in a batch. Feels like photos developing.
  - **Job progress**: progress bar uses the accent gradient, width animates smoothly. Status text cross-fades.
- **Reduced motion:** all animations respect `prefers-reduced-motion` — fall back to instant state changes, no aurora.

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-20 | Studio Dark aesthetic with aurora accent | User wanted "creative tool" feel over purely professional; accent differentiates from competitors using flat blue/purple |
| 2026-06-20 | Cabinet Grotesk + Plus Jakarta Sans | Cabinet gives "modern creative" feel vs Inter's "enterprise"; Plus Jakarta has better CJK fallback than Geist |
| 2026-06-20 | Gallery-wall library posture | Images are first-class objects, not table rows — reinforces "your creative home base" positioning |
| 2026-06-20 | Generation canvas, not form | User said target users hate the官方 UI's form-like flow; we make it a workspace |
| 2026-06-20 | Aurora as signature flourish | Single signature motion = memorable; evokes photographic developer = on-brand for image generation |
