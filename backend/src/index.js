import cron from 'node-cron';
import express from 'express';

import { getLatestDigest, loadDigests } from './digest/store.js';
import { digestState, runDigestJob } from './jobs/runDigest.js';
import { ensureGitRepo } from './utils/git.js';

const app = express();
const port = Number(process.env.PORT || 3000);
const cronSchedule = process.env.CRON_SCHEDULE || '0 8 * * *';
const cronSecret = process.env.CRON_SECRET;

app.use(express.json());

app.use((_req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type');
  if (_req.method === 'OPTIONS') {
    res.status(204).end();
    return;
  }
  next();
});

app.get('/health', (_req, res) => {
  res.json({
    ok: true,
    running: digestState.running,
    schedule: cronSchedule,
    lastRun: digestState.lastRun,
  });
});

/**
 * Public daily news API.
 * - GET /api/digest          → latest digest only
 * - GET /api/digest?limit=5  → newest N digests (max 50)
 */
app.get('/api/digest', (req, res) => {
  try {
    const digests = loadDigests();
    if (digests.length === 0) {
      res.status(404).json({ ok: false, error: 'No digests available yet' });
      return;
    }

    const rawLimit = req.query.limit;
    if (rawLimit === undefined) {
      res.json({ ok: true, digest: digests[0] });
      return;
    }

    const limit = Math.min(Math.max(Number.parseInt(String(rawLimit), 10) || 1, 1), 50);
    res.json({ ok: true, count: Math.min(limit, digests.length), digests: digests.slice(0, limit) });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    res.status(500).json({ ok: false, error: message });
  }
});

app.get('/api/digest/latest', (_req, res) => {
  try {
    const digest = getLatestDigest();
    if (!digest) {
      res.status(404).json({ ok: false, error: 'No digests available yet' });
      return;
    }
    res.json({ ok: true, digest });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    res.status(500).json({ ok: false, error: message });
  }
});

app.get('/api/digest/status', (_req, res) => {
  res.json({
    running: digestState.running,
    schedule: cronSchedule,
    lastRun: digestState.lastRun,
  });
});

app.post('/api/digest/run', async (req, res) => {
  if (cronSecret) {
    const auth = req.headers.authorization || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    if (token !== cronSecret) {
      res.status(401).json({ error: 'Unauthorized' });
      return;
    }
  }

  const forceRequested =
    req.query.force === 'true' ||
    req.query.force === '1' ||
    req.body?.force === true;

  // Cost guard: same-day force re-runs call Claude again. Opt in via ALLOW_FORCE_DIGEST=true.
  const forceAllowed = process.env.ALLOW_FORCE_DIGEST?.toLowerCase() === 'true';
  if (forceRequested && !forceAllowed) {
    res.status(403).json({
      ok: false,
      error:
        'force=true is disabled to avoid extra Claude charges. Set ALLOW_FORCE_DIGEST=true on Railway to override.',
    });
    return;
  }

  try {
    const result = await runDigestJob({ force: forceRequested && forceAllowed, trigger: 'api' });
    res.json({ ok: true, result });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const status = message.includes('already running') ? 409 : 500;
    res.status(status).json({ ok: false, error: message, lastRun: digestState.lastRun });
  }
});

async function start() {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn('[server] ANTHROPIC_API_KEY is not set — digest runs will fail');
  }

  if (!process.env.TELEMETRY_INGESTION_KEY || !process.env.AGENT_API_KEY_ID) {
    console.warn('[telemetry] TELEMETRY_INGESTION_KEY or AGENT_API_KEY_ID not set — Zanshin events disabled');
  } else {
    console.log('[telemetry] Zanshin reporting enabled');
  }

  if (!cron.validate(cronSchedule)) {
    throw new Error(`Invalid CRON_SCHEDULE: ${cronSchedule}`);
  }

  try {
    await ensureGitRepo();
    console.log('[git] Repository ready for commits');
  } catch (error) {
    console.warn(`[git] Startup git setup skipped: ${error instanceof Error ? error.message : error}`);
  }

  cron.schedule(
    cronSchedule,
    () => {
      runDigestJob({ trigger: 'cron' }).catch((error) => {
        console.error(`[cron] Scheduled run failed: ${error instanceof Error ? error.message : error}`);
      });
    },
    { timezone: 'UTC' },
  );

  app.listen(port, () => {
    console.log(`[server] Listening on :${port}`);
    console.log(`[cron] Schedule: ${cronSchedule} (UTC)`);
  });
}

start().catch((error) => {
  console.error('[server] Failed to start:', error);
  process.exit(1);
});
