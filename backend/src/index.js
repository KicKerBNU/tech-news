import cron from 'node-cron';
import express from 'express';

import { getLatestDigest, hasDigestForToday, loadDigests } from './digest/store.js';
import { digestState, runDigestJob } from './jobs/runDigest.js';
import { ensureGitRepo } from './utils/git.js';

const app = express();
const port = Number(process.env.PORT || 3000);
const cronSchedule = process.env.CRON_SCHEDULE || '0 8 * * *';
const retrySchedule = process.env.CRON_RETRY_SCHEDULE || '*/5 * * * *';
const maxCatchUpAttempts = Number(process.env.CRON_RETRY_MAX_ATTEMPTS || 20);
const cronSecret = process.env.CRON_SECRET;

/** @type {{ day: string | null, attempts: number, exhausted: boolean }} */
const catchUpState = {
  day: null,
  attempts: 0,
  exhausted: false,
};

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

/** Parse "m h ..." cron; returns { minute, hour } or null. */
function parseDailyCron(schedule) {
  const parts = String(schedule).trim().split(/\s+/);
  if (parts.length < 2) return null;
  const minute = Number(parts[0]);
  const hour = Number(parts[1]);
  if (!Number.isInteger(minute) || !Number.isInteger(hour)) return null;
  if (minute < 0 || minute > 59 || hour < 0 || hour > 23) return null;
  return { minute, hour };
}

function isPastPrimarySchedule(now = new Date()) {
  const parsed = parseDailyCron(cronSchedule);
  if (!parsed) {
    // Unknown cron shape — allow catch-up anytime.
    return true;
  }

  const minutesNow = now.getUTCHours() * 60 + now.getUTCMinutes();
  const minutesPrimary = parsed.hour * 60 + parsed.minute;
  return minutesNow >= minutesPrimary;
}

function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}

function resetCatchUpIfNewDay() {
  const day = todayUtc();
  if (catchUpState.day !== day) {
    catchUpState.day = day;
    catchUpState.attempts = 0;
    catchUpState.exhausted = false;
  }
}

/**
 * Catch-up: if today's digest is missing after the primary cron window,
 * try again (idempotent — Claude is skipped once today's entry exists).
 * Stops after CRON_RETRY_MAX_ATTEMPTS (default 20) failures for the UTC day.
 */
async function maybeRunCatchUp() {
  resetCatchUpIfNewDay();

  if (digestState.running) {
    console.log('[retry] Digest already running — skipping catch-up');
    return;
  }

  if (!isPastPrimarySchedule()) {
    return;
  }

  if (hasDigestForToday()) {
    catchUpState.attempts = 0;
    catchUpState.exhausted = false;
    return;
  }

  if (catchUpState.exhausted || catchUpState.attempts >= maxCatchUpAttempts) {
    if (!catchUpState.exhausted) {
      catchUpState.exhausted = true;
      console.error(
        `[retry] Giving up for ${catchUpState.day} after ${maxCatchUpAttempts} catch-up attempts`,
      );
    }
    return;
  }

  catchUpState.attempts += 1;
  console.log(
    `[retry] No digest for today yet — catch-up attempt ${catchUpState.attempts}/${maxCatchUpAttempts}`,
  );

  try {
    await runDigestJob({ trigger: 'retry' });
    if (hasDigestForToday()) {
      catchUpState.attempts = 0;
      catchUpState.exhausted = false;
    }
  } catch (error) {
    console.error(`[retry] Catch-up failed: ${error instanceof Error ? error.message : error}`);
    if (catchUpState.attempts >= maxCatchUpAttempts) {
      catchUpState.exhausted = true;
      console.error(
        `[retry] Giving up for ${catchUpState.day} after ${maxCatchUpAttempts} catch-up attempts`,
      );
    }
  }
}

app.get('/health', (_req, res) => {
  resetCatchUpIfNewDay();
  res.json({
    ok: true,
    running: digestState.running,
    schedule: cronSchedule,
    retrySchedule,
    maxCatchUpAttempts,
    catchUpAttempts: catchUpState.attempts,
    catchUpExhausted: catchUpState.exhausted,
    hasDigestForToday: hasDigestForToday(),
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
  resetCatchUpIfNewDay();
  res.json({
    running: digestState.running,
    schedule: cronSchedule,
    retrySchedule,
    maxCatchUpAttempts,
    catchUpAttempts: catchUpState.attempts,
    catchUpExhausted: catchUpState.exhausted,
    hasDigestForToday: hasDigestForToday(),
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

app.post('/api/alert/test', async (req, res) => {
  if (cronSecret) {
    const auth = req.headers.authorization || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    if (token !== cronSecret) {
      res.status(401).json({ error: 'Unauthorized' });
      return;
    }
  }

  const { sendFailureAlert } = await import('./utils/alertEmail.js');
  const result = await sendFailureAlert({
    trigger: 'alert-test',
    error: 'Manual test of SIGNAL failure alerts (safe to ignore).',
    startedAt: new Date().toISOString(),
    force: true,
  });
  res.status(result.sent ? 200 : 400).json({ ok: result.sent, ...result });
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
  if (!cron.validate(retrySchedule)) {
    throw new Error(`Invalid CRON_RETRY_SCHEDULE: ${retrySchedule}`);
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

  // If the primary run fails (e.g. GitHub temporary limits), keep trying every 5 minutes
  // until today's digest exists. Idempotent — no Claude call once today is done.
  cron.schedule(
    retrySchedule,
    () => {
      maybeRunCatchUp().catch((error) => {
        console.error(`[retry] Unexpected catch-up error: ${error instanceof Error ? error.message : error}`);
      });
    },
    { timezone: 'UTC' },
  );

  app.listen(port, () => {
    console.log(`[server] Listening on :${port}`);
    console.log(`[cron] Primary schedule: ${cronSchedule} (UTC)`);
    console.log(`[cron] Catch-up retry: ${retrySchedule} (UTC), max ${maxCatchUpAttempts} attempts/day`);
  });

  // If we boot after 08:00 UTC and today is still missing, try once immediately.
  maybeRunCatchUp().catch((error) => {
    console.error(`[retry] Startup catch-up failed: ${error instanceof Error ? error.message : error}`);
  });
}

start().catch((error) => {
  console.error('[server] Failed to start:', error);
  process.exit(1);
});
