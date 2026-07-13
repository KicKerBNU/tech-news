# SIGNAL — Autonomous AI/Tech News Wire

Repo: https://github.com/KicKerBNU/tech-news

Fully autonomous pipeline: GitHub Actions runs the agent every 10 minutes,
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

## 2. Add your API key as a secret

In the repo: **Settings → Secrets and variables → Actions → New repository secret**
- Name: `ANTHROPIC_API_KEY`
- Value: your Anthropic API key

## 3. Enable Actions (if needed)

Go to the **Actions** tab of your repo and enable workflows if prompted.
The workflow is already set to run every 10 minutes (`.github/workflows/digest.yml`).
You can also trigger a run manually from that tab (**Run workflow** button)
to confirm it works without waiting.

## 4. Data URL is already wired in

`webapp/src/App.vue` already points at:

```
https://raw.githubusercontent.com/KicKerBNU/tech-news/main/digests/data.json
```

Nothing to change — this works as-is once you push to `main`. If you ever
fork or rename the repo, either edit that line or set an environment
variable in Netlify instead (no code edit needed):

- Variable name: `VITE_DATA_URL`
- Value: `https://raw.githubusercontent.com/<you>/<repo>/main/digests/data.json`

## 5. Deploy to Netlify

- New site from Git → pick this repo
- Netlify will read `netlify.toml` automatically (base: `webapp`, build: `npm run build`, publish: `webapp/dist`)
- If you set `VITE_DATA_URL` above, add it under **Site settings → Environment variables**

That's it. Once the first Action run completes and pushes a commit,
the site will show it on its next 10-minute poll (or on page reload).

## Webapp architecture (DDD-layered, Vue 3 + Composition API + Pinia + Router + Tailwind v4)

```
webapp/src/
  domain/digest/DigestEntry.js         entity — formatting that's actually domain logic (stamp, relativeAge)
  infrastructure/http/                 the one place that knows data comes from raw.githubusercontent.com
  application/stores/digestStore.js    Pinia store — orchestrates repository + state, single source of truth
  presentation/
    views/          FeedView.vue, EntryDetailView.vue
    components/     AppHeader.vue, DigestCard.vue, EmptyState.vue  (DigestCard reused on both views — DRY)
    composables/     useClock.js, usePolling.js                     (reusable, framework-facing logic)
    styles/global.css                  design tokens, defined once
  router/index.js    "/" (feed) and "/entry/:id" (single transmission — reachable via a real permalink)
  shared/utils/time.js                 generic formatting with no domain meaning (clock, countdown)
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

- **Timing isn't exact.** GitHub's own docs note that scheduled workflow
  runs can be delayed during periods of high platform load — 10 minutes is
  the target, not a guarantee.
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
