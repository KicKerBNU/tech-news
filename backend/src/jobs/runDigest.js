import path from 'node:path';

import { run } from '../utils/exec.js';
import { commitDigestIfChanged, ensureGitRepo, getRepoRoot, syncLatest } from '../utils/git.js';

const PYTHON = process.env.PYTHON_BIN || 'python3';

/** @type {{ running: boolean, lastRun: object|null }} */
export const digestState = {
  running: false,
  lastRun: null,
};

function agentEnv(extra = {}) {
  return {
    ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
    HONEYCOMB_API_KEY: process.env.HONEYCOMB_API_KEY,
    OTEL_SERVICE_NAME: process.env.OTEL_SERVICE_NAME || 'signal-news-digest',
    OTEL_EXPORTER_OTLP_ENDPOINT: process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'https://api.honeycomb.io',
    RESEND_API_KEY: process.env.RESEND_API_KEY,
    RESEND_FROM_EMAIL: process.env.RESEND_FROM_EMAIL,
    UNSUBSCRIBE_SECRET: process.env.UNSUBSCRIBE_SECRET,
    TELEGRAM_BOT_TOKEN: process.env.TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID: process.env.TELEGRAM_CHAT_ID,
    TELEGRAM_THREAD_ID: process.env.TELEGRAM_THREAD_ID,
    SITE_URL: process.env.SITE_URL || 'https://signal-news-agent.netlify.app',
    ...extra,
  };
}

async function runPython(script, env = {}) {
  const repoRoot = getRepoRoot();
  const output = await run(PYTHON, [path.join('agent', script)], {
    cwd: repoRoot,
    env: agentEnv(env),
    label: script,
  });
  if (output) {
    console.log(`[${script}] ${output}`);
  }
}

/**
 * @param {{ force?: boolean, trigger?: string }} options
 */
export async function runDigestJob(options = {}) {
  const { force = false, trigger = 'manual' } = options;

  if (digestState.running) {
    throw new Error('Digest job is already running');
  }

  digestState.running = true;
  const startedAt = new Date().toISOString();
  console.log(`[digest] Starting job (trigger=${trigger}, force=${force})`);

  try {
    await ensureGitRepo();
    await syncLatest();

    await runPython('news_digest.py', force ? { FORCE_DIGEST: 'true' } : {});

    const changed = await commitDigestIfChanged();

    if (changed) {
      for (const script of ['send_newsletter.py', 'send_telegram.py']) {
        try {
          await runPython(script);
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          console.error(`[digest] ${script} failed (digest was committed): ${message}`);
        }
      }
    } else {
      console.log('[digest] Skipping newsletter/Telegram — no new digest committed');
    }

    digestState.lastRun = {
      startedAt,
      finishedAt: new Date().toISOString(),
      trigger,
      force,
      changed,
      status: 'success',
      error: null,
    };

    return digestState.lastRun;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[digest] Job failed: ${message}`);

    digestState.lastRun = {
      startedAt,
      finishedAt: new Date().toISOString(),
      trigger,
      force,
      changed: false,
      status: 'error',
      error: message,
    };

    throw error;
  } finally {
    digestState.running = false;
  }
}
