# SIGNAL — Autonomous AI/Tech News Wire

Repo: https://github.com/KicKerBNU/tech-news

Fully autonomous pipeline: an Express backend on **Railway** runs the digest agent daily,
commits results to `digests/data.json`, and a Vue app on Netlify polls that file to show
a live feed.

## Architecture

```
Railway (Express + node-cron)
  → python agent/news_digest.py
  → git commit + push digests/data.json
  → send_newsletter.py + send_telegram.py

Netlify (Vue webapp + subscribe/unsubscribe functions)
  → polls raw.githubusercontent.com/.../digests/data.json
```

## 1. Push this to the repo

```bash
git clone https://github.com/KicKerBNU/tech-news.git
cd tech-news
git add .
git commit -m "initial: autonomous news wire agent + webapp"
git push
```

## 2. Deploy the backend to Railway

1. [railway.app](https://railway.app) → **New project** → **Deploy from GitHub repo** → pick this repo
2. Railway reads `railway.toml` + `Dockerfile` (Node 20 + Python 3 + git)
3. Add **Variables** (Settings → Variables):

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | yes | Claude API for the digest agent |
| `GITHUB_TOKEN` | yes | Fine-grained PAT with **Contents: read and write** on this repo |
| `CRON_SECRET` | recommended | Protects `POST /api/digest/run` (manual trigger) |
| `CRON_SCHEDULE` | no | Default `0 8 * * *` (08:00 UTC daily) |
| `HONEYCOMB_API_KEY` | no | OpenTelemetry traces |
| `RESEND_API_KEY` | no | Newsletter delivery |
| `RESEND_FROM_EMAIL` | no | e.g. `SIGNAL <newsletter@yourdomain.com>` |
| `UNSUBSCRIBE_SECRET` | no | Signed unsubscribe links |
| `TELEGRAM_BOT_TOKEN` | no | Telegram bot token |
| `TELEGRAM_CHAT_ID` | no | Group chat id |
| `SITE_URL` | no | Default `https://signal-news-agent.netlify.app` |

**GitHub token:** Settings → Developer settings → Fine-grained tokens → grant access to
`KicKerBNU/tech-news` with **Contents: read and write**. The backend uses it to push digest commits.

4. Deploy. Check logs for `[server] Listening` and `[cron] Schedule: 0 8 * * * (UTC)`.
5. Hit `https://<your-railway-domain>/health` — should return `{ ok: true, ... }`.

### Manual run (don't wait for cron)

```bash
curl -X POST "https://<your-railway-domain>/api/digest/run" \
  -H "Authorization: Bearer YOUR_CRON_SECRET"
```

Add `?force=true` to re-run even if today's digest already exists.

### Local backend dev

```bash
cd backend
yarn install
cp ../.env.example ../.env   # fill in keys
yarn dev
```

Requires Python 3.11+ with `pip install -r agent/requirements.txt`.

Copy `.env.example` to `.env` for local runs. Never commit API keys.

## 3. Data URL is already wired in

`webapp/src/App.vue` already points at:

```
https://raw.githubusercontent.com/KicKerBNU/tech-news/master/digests/data.json
```

Nothing to change — this works as-is once the backend pushes to `master`. If you ever
fork or rename the repo, either edit that line or set an environment
variable in Netlify instead (no code edit needed):

- Variable name: `VITE_DATA_URL`
- Value: `https://raw.githubusercontent.com/<you>/<repo>/master/digests/data.json`

## 4. Deploy to Netlify

- New site from Git → pick this repo
- Netlify will read `netlify.toml` automatically (base: `webapp`, build: `yarn build`, publish: `webapp/dist`)
- If you set `VITE_DATA_URL` above, add it under **Site settings → Environment variables**
- For newsletter subscribe/unsubscribe, set on Netlify: `RESEND_API_KEY`, `UNSUBSCRIBE_SECRET`

That's it. Once the backend completes its first run and pushes a commit,
the site will show it on its next poll (or on page reload).

## 5. Newsletter (email digest)

Subscribers enter their email on the site; after each daily digest run, the backend emails them the latest transmission. **No database required** — subscribers are stored as [Resend Contacts](https://resend.com/docs/dashboard/audiences/contacts).

### One-time setup

1. **Resend** — [resend.com](https://resend.com) → create an API key with **Full access** (send-only keys cannot add subscribers)
2. **POC / no domain** — use `RESEND_FROM_EMAIL=SIGNAL <onboarding@resend.dev>`. Resend only delivers to the email you signed up with (sandbox limit).
3. **Unsubscribe secret** — generate a random string:
   ```bash
   openssl rand -base64 32
   ```
4. **Railway env vars** — `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `UNSUBSCRIBE_SECRET`
5. **Netlify env vars** — same `RESEND_API_KEY` and `UNSUBSCRIBE_SECRET` (for subscribe/unsubscribe functions)
6. Redeploy Netlify after adding env vars

### Flow

```
Visitor → Subscribe form → Netlify Function → Resend Contacts
Daily cron → digest agent → commit data.json → send_newsletter.py → Resend → inbox
```

Each email includes a signed unsubscribe link (`/unsubscribe?email=…&sig=…`).

## 6. Telegram group posts

After each daily digest, the backend can post the latest transmission to a Telegram group via the **Bot API**.

> **Personal account vs bot:** Messages will appear from your **bot**, not your personal user. That's the supported way to automate posts.

### One-time setup

1. Open Telegram → message **@BotFather** → `/newbot` → copy the **token**
2. Add the bot to your group (promote to admin if the group restricts posting)
3. Send any message in the group, then open in a browser:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Copy `message.chat.id` (groups are negative numbers like `-1001234567890`)
4. Add Railway env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
5. Optional: `TELEGRAM_THREAD_ID` if posting into a specific topic in a forum group

### Test locally

```bash
cd agent
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python send_telegram.py
```

### Flow

```
Daily cron → digest agent → commit data.json → send_telegram.py → Telegram group
```

## Webapp architecture (DDD-layered, Vue 3 + Composition API + Pinia + Router + Tailwind v4)

```
webapp/src/
  domain/digest/DigestEntry.js         entity — formatting that's actually domain logic (stamp, relativeAge)
  infrastructure/http/                 the one place that knows data comes from raw.githubusercontent.com
  application/stores/digestStore.js    Pinia store — orchestrates repository + state, single source of truth
  presentation/
    views/          FeedView.vue, EntryDetailView.vue, UnsubscribeView.vue
    components/     AppHeader.vue, DigestCard.vue, EmptyState.vue, NewsletterSubscribe.vue
    composables/     useClock.js, usePolling.js                     (reusable, framework-facing logic)
    styles/global.css                  design tokens, defined once
  router/index.js    "/" (feed) and "/entry/:id" (single transmission — reachable via a real permalink)
  shared/utils/time.js                 generic formatting with no domain meaning (clock, countdown)
```

## Backend (`backend/`)

```
backend/src/
  index.js              Express server, health check, cron scheduler, manual trigger API
  jobs/runDigest.js     Orchestrates pull → agent → commit → newsletter → telegram
  utils/git.js          Clone/sync repo and push digest commits via GITHUB_TOKEN
  utils/exec.js         Child-process helper for python/git commands
```

## Honeycomb tracing (OpenTelemetry)

The digest agent exports traces to Honeycomb when `HONEYCOMB_API_KEY` is set.

**Dataset:** `signal-news-digest`

**Custom spans:**
- `digest.run` — full daily job
- `digest.call_claude` — Anthropic API + web search (auto-instrumented httpx child spans)
- `digest.load_entries` / `digest.save_entries` — JSON I/O

**Verify locally:**
```bash
cd agent
pip install -r requirements.txt
export HONEYCOMB_API_KEY=your-key
python verify_traces.py
```

Deliberately **not** included, per YAGNI: no repository interface/abstract class
(there's one data source, so one concrete implementation is enough — add an
interface if a second source ever shows up), no Vuex-style modules-within-modules,
no generic CRUD abstractions. The layering exists to separate "what a digest is"
from "how we fetch it" from "how Vue renders it" — nothing more.

**Styling** uses Tailwind v4 (the `@tailwindcss/vite` plugin, no separate
`tailwind.config.js` needed). All colors/fonts are defined once, in
`presentation/styles/global.css`, inside an `@theme` block — that's the single
source of truth for the design tokens, and Tailwind generates utility classes
(`bg-surface`, `text-accent`, `border-border`, etc.) straight from it. No
scoped `<style>` blocks left in components — DRY means the palette lives in
exactly one file, not copy-pasted across five component `<style>` tags.

## Notes / things worth knowing

- **Scheduler runs on Railway**, not GitHub Actions. The service stays up 24/7; `node-cron`
  fires at the configured UTC time. Railway also health-checks `/health` and restarts on failure.
- **Same-day idempotency** — if today's digest already exists (UTC date), the agent skips unless
  you trigger with `force=true`.
- **Push triggers redeploy** — each digest commit may redeploy the Railway service if auto-deploy
  is on. That's fine; the job finishes before the new container starts.
- **Raw file caching.** `raw.githubusercontent.com` caches for a few minutes;
  the app cache-busts each fetch, but very rapid manual reloads may still show
  a slightly stale copy.
- **To change the schedule:** set `CRON_SCHEDULE` on Railway (standard cron syntax, UTC).
