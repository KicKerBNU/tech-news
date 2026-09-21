# SIGNAL — Autonomous AI/Tech News Wire

Repo: https://github.com/KicKerBNU/tech-news

Fully autonomous pipeline: an Express backend on **Railway** runs the digest agent daily,
commits results to `digests/data.json`, and a Vue app on Netlify polls that file to show
a live feed.

## Architecture

```
Railway (Express + node-cron)
  → python agent/news_digest.py
       → crawl agent/sources.json (RSS-first, HTML fallback)
       → cheap LLM refine (Haiku / gpt-5-nano, no web_search)
  → git commit + push digests/data.json
  → send_newsletter.py + send_telegram.py

Netlify (Vue webapp + subscribe/unsubscribe functions)
  → polls raw.githubusercontent.com/.../digests/data.json
```

Discovery is free (HTTP crawl). The LLM only picks and rewrites 2–5 stories from
that candidate list, so daily cost stays near one short completion — not paid
web_search with tens of thousands of tokens.

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
| `OPENAI_API_KEY` | recommended | Fallback if Claude fails twice (`gpt-5-nano`, cheap) |
| `GITHUB_TOKEN` | yes | Fine-grained PAT with **Contents: read and write** on this repo |
| `CRON_SECRET` | recommended | Protects `POST /api/digest/run` (manual trigger) |
| `CRON_SCHEDULE` | no | Default `0 8 * * *` (08:00 UTC daily) |
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

### Public news API

```bash
# Latest daily digest
curl -sS "https://tech-news-production-af46.up.railway.app/api/digest"

# Or alias
curl -sS "https://tech-news-production-af46.up.railway.app/api/digest/latest"

# Recent history (newest first, max 50)
curl -sS "https://tech-news-production-af46.up.railway.app/api/digest?limit=5"
```

No auth required — same content as Telegram/email/the website feed.

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

## Digest quality: crawl + refine (no paid search)

The agent **crawls** preferred outlets, then uses a cheap LLM **without** web_search
to pick and rewrite 2–5 stories. It should not rehash yesterday's stories or lean
on weak aggregators.

### Preferred outlets (`agent/sources.json`)

Edit this file anytime — the next digest run loads it automatically (no code change).

```json
{
  "preferred": [
    {
      "name": "TechCrunch",
      "url": "https://techcrunch.com",
      "rss": "https://techcrunch.com/feed/",
      "topics": ["startups", "AI"]
    }
  ],
  "avoid": [
    "Tech Startups",
    "Build Fast with AI"
  ]
}
```

| Field | Purpose |
|-------|---------|
| `preferred[].name` | Outlet name cited in the digest |
| `preferred[].url` | Homepage / listing page (HTML fallback if RSS fails) |
| `preferred[].rss` | Optional RSS/Atom feed (preferred crawl path). Use `null` for hard paywalls |
| `avoid` | Aggregators / weak sources not to use as the primary citation |

**How to grow the list:** add a new object under `preferred` (with `rss` when available), commit, push to `master`. Railway's next cron (or catch-up) will use it.

Hard paywalls (Bloomberg, FT, WSJ, The Information) can omit `rss`; the crawler soft-skips them instead of burning retries.

### Deduping against recent digests

Each run:

1. Crawls preferred feeds/pages (~last 36 hours), caps ~40 candidates
2. Drops candidates that look like the last **2** digests' headlines/bullets
3. Asks Haiku (then nano) to pick 2–5 from the remaining list and write the digest JSON
4. **Rejects** the result if too many bullets still look like near-duplicates (retries kick in)

So a story that already shipped yesterday should not appear again unless there is a genuine new development.

### Model fallback (cost-aware)

1. Crawl preferred sources (no LLM)  
2. Claude Haiku refine — up to 2 attempts, **no tools**  
3. If both fail → OpenAI `gpt-5-nano` — up to 2 attempts (needs `OPENAI_API_KEY`)  
4. Empty / placeholder digests (“no major news”) are rejected  

## Backend (`backend/`)

```
backend/src/
  index.js              Express server, health check, cron scheduler, manual trigger API
  jobs/runDigest.js     Orchestrates pull → agent → commit → newsletter → telegram
  utils/git.js          Clone/sync repo and push digest commits via GITHUB_TOKEN
  utils/exec.js         Child-process helper for python/git commands

agent/
  news_digest.py        Crawl preferred outlets → cheap LLM refine (+ OpenAI fallback)
  crawl_sources.py      RSS-first / HTML fallback crawler
  sources.json          Preferred / avoid outlets + optional rss feeds
  send_newsletter.py    Resend batch email
  send_telegram.py      Telegram Bot API post
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
- **Catch-up retries:** if the primary run fails (e.g. GitHub temporary rate limits) and today's
  digest is still missing, a second cron (`CRON_RETRY_SCHEDULE`, default every 5 minutes) keeps
  trying until it succeeds or hits `CRON_RETRY_MAX_ATTEMPTS` (default **20**). Once today's entry
  exists, retries are no-ops (no extra LLM refine calls). Git fetch/push also retries with backoff on
  transient errors.
- **Failure email:** when a digest job fails, Resend emails the same active contacts as the
  newsletter (once per UTC day so retries won't spam). Uses existing `RESEND_API_KEY` /
  `RESEND_FROM_EMAIL` — no extra env var.
- **Same-day idempotency** — if today's digest already exists (UTC date), the agent skips unless
  you trigger with `force=true` (and `ALLOW_FORCE_DIGEST=true`).
- **Push triggers redeploy** — each digest commit may redeploy the Railway service if auto-deploy
  is on. That's fine; the job finishes before the new container starts.
- **Raw file caching.** `raw.githubusercontent.com` caches for a few minutes;
  the app cache-busts each fetch, but very rapid manual reloads may still show
  a slightly stale copy.
- **Digest sources + dedupe:** see [Digest quality: crawl + refine](#digest-quality-crawl--refine-no-paid-search).
  Edit `agent/sources.json` to grow preferred outlets; recent digests are excluded from the next run.
- **To change the schedule:** set `CRON_SCHEDULE` on Railway (standard cron syntax, UTC).
