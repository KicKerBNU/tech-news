import cron from 'node-cron';
import express from 'express';

import { digestState, runDigestJob } from './jobs/runDigest.js';
import { ensureGitRepo } from './utils/git.js';

const app = express();
const port = Number(process.env.PORT || 3000);
const cronSchedule = process.env.CRON_SCHEDULE || '0 8 * * *';
const cronSecret = process.env.CRON_SECRET;

app.use(express.json());

app.get('/health', (_req, res) => {
  res.json({
    ok: true,
    running: digestState.running,
    schedule: cronSchedule,
    lastRun: digestState.lastRun,
  });
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

  const force =
    req.query.force === 'true' ||
    req.query.force === '1' ||
    req.body?.force === true;

  try {
    const result = await runDigestJob({ force, trigger: 'api' });
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
