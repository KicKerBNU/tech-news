# SIGNAL — Autonomous AI/Tech News Wire

Repo: https://github.com/KicKerBNU/tech-news

Fully autonomous pipeline: GitHub Actions runs the agent daily (08:00 UTC primary, 11:00 UTC backup),
commits results to `digests/data.json`, and a Vue app on Netlify polls that
file to show a live feed. No server, no human step after setup.

## 1. Push this to the repo

```bash
git clone https://github.com/KicKerBNU/tech-news.git
cd tech-news
# copy all files from this folder in, then:
git add .
git commit -m "initial: autonomous news wire agent + webapp"
git push
```

## 2. Add your API keys as secrets

In the repo: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Purpose |
|------|---------|
| `ANTHROPIC_API_KEY` | Claude API for the digest agent |
| `HONEYCOMB_API_KEY` | OpenTelemetry traces to Honeycomb (optional) |
| `RESEND_API_KEY` | Newsletter — subscribers + email delivery |
| `RESEND_FROM_EMAIL` | e.g. `SIGNAL <newsletter@yourdomain.com>` |
| `UNSUBSCRIBE_SECRET` | Random string for signed unsubscribe links |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather (optional) |
| `TELEGRAM_CHAT_ID` | Group chat id, e.g. `-1001234567890` (optional) |

Copy `.env.example` to `.env` for local runs. Never commit API keys.

## 3. Enable Actions (if needed)

Go to the **Actions** tab of your repo and enable workflows if prompted.
The workflow runs daily at 08:00 UTC with an 11:00 UTC backup slot (`.github/workflows/digest.yml`).
If the first run succeeds, the second is a no-op (same-day idempotency).
You can also trigger a run manually from that tab (**Run workflow** button)
to confirm it works without waiting.

## 4. Data URL is already wired in

`webapp/src/App.vue` already points at:

```
https://raw.githubusercontent.com/KicKerBNU/tech-news/master/digests/data.json
```

Nothing to change — this works as-is once you push to `master`. If you ever
fork or rename the repo, either edit that line or set an environment
variable in Netlify instead (no code edit needed):

- Variable name: `VITE_DATA_URL`
- Value: `https://raw.githubusercontent.com/<you>/<repo>/master/digests/data.json`

## 5. Deploy to Netlify

- New site from Git → pick this repo
- Netlify will read `netlify.toml` automatically (base: `webapp`, build: `yarn build`, publish: `webapp/dist`)
- If you set `VITE_DATA_URL` above, add it under **Site settings → Environment variables**
- For newsletter subscribe/unsubscribe, set on Netlify: `RESEND_API_KEY`, `UNSUBSCRIBE_SECRET`

That's it. Once the first Action run completes and pushes a commit,
the site will show it on its next poll (or on page reload).

## 6. Newsletter (email digest)

Subscribers enter their email on the site; after each daily digest run, GitHub Actions emails them the latest transmission. **No database required** — subscribers are stored as [Resend Contacts](https://resend.com/docs/dashboard/audiences/contacts).

### One-time setup

1. **Resend** — [resend.com](https://resend.com) → create an API key with **Full access** (send-only keys cannot add subscribers)
2. **POC / no domain** — use `RESEND_FROM_EMAIL=SIGNAL <onboarding@resend.dev>`. Resend only delivers to the email you signed up with (sandbox limit).
3. **Unsubscribe secret** — generate a random string:
   ```bash
   openssl rand -base64 32
   ```
4. **GitHub Secrets** — `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `UNSUBSCRIBE_SECRET`
5. **Netlify env vars** — same `RESEND_API_KEY` and `UNSUBSCRIBE_SECRET` (for subscribe/unsubscribe functions)
6. Redeploy Netlify after adding env vars

### Flow

```
Visitor → Subscribe form → Netlify Function → Resend Contacts
Daily cron → digest agent → commit data.json → send_newsletter.py → Resend → inbox
```

Each email includes a signed unsubscribe link (`/unsubscribe?email=…&sig=…`).

## 7. Telegram group posts

After each daily digest, GitHub Actions can post the latest transmission to a Telegram group via the **Bot API** (recommended — stable and works in CI).

> **Personal account vs bot:** Messages will appear from your **bot**, not your personal user. That's the supported way to automate posts. You can name/avatar the bot to match SIGNAL. Posting as your personal account would require unofficial user-client APIs (Telethon), phone/session storage, and is fragile in GitHub Actions — not recommended.

### One-time setup

1. Open Telegram → message **@BotFather** → `/newbot` → copy the **token**
2. Add the bot to your group (promote to admin if the group restricts posting)
3. Send any message in the group, then open in a browser:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Copy `message.chat.id` (groups are negative numbers like `-1001234567890`)
4. Add GitHub Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
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

**Verify in Honeycomb UI** (query-patterns skill):
- `COUNT` grouped by `name` — see span volume per operation
- `P99(duration_ms)` where `name = digest.call_claude` — Claude latency tail
- `COUNT` where `error = true` grouped by `exception.slug` — failure sites

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

- **Timing isn't exact.** GitHub's own docs note that scheduled workflow
  runs can be delayed during periods of high platform load — often by 1–3+ hours,
  and sometimes skipped entirely on busy days. This repo mitigates that with:
  - **Two cron slots** (08:00 and 11:00 UTC) — only the first successful run
    writes a digest; the backup skips if today already has an entry.
  - **`workflow_dispatch`** — Actions → *News Digest Agent* → *Run workflow*
    (check *force* to re-run even if today already has a digest).
  - **Optional external trigger** — a free cron service (e.g. [cron-job.org](https://cron-job.org))
    can POST to GitHub's API to fire `workflow_dispatch` or `repository_dispatch`
    (`run-digest`) if you want a third, independent clock. Requires a fine-grained
    PAT with *Actions: write* on this repo.
- **Inactive repos pause schedules.** GitHub automatically disables scheduled
  workflows after 60 days with no repository activity. Since this workflow
  commits on every successful run, the repo stays active on its own — but if
  you pause it manually for a long stretch, you may need to re-enable the
  schedule from the Actions tab afterward.
- **Raw file caching.** `raw.githubusercontent.com` caches for a few minutes;
  the app cache-busts each fetch, but very rapid manual reloads may still show
  a slightly stale copy.
- **To change the interval later:** edit the `cron:` line in
  `.github/workflows/digest.yml` (GitHub's minimum is every 5 minutes) —
  nothing else needs to change.
