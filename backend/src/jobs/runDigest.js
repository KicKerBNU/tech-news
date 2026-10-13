import path from 'node:path';

import { getLatestDigest, hasDigestForToday } from '../digest/store.js';
import { telemetry } from '../telemetry.ts';
import { clearFailureAlertDebounce, sendFailureAlert } from '../utils/alertEmail.js';
import { run } from '../utils/exec.js';
import { commitDigestIfChanged, ensureGitRepo, getRepoRoot, syncLatest } from '../utils/git.js';

const PYTHON = process.env.PYTHON_BIN || 'python3';
const SITE_URL = (process.env.SITE_URL || 'https://signal-news-agent.netlify.app').replace(/\/$/, '');

/** @type {{ running: boolean, lastRun: object|null }} */
export const digestState = {
  running: false,
  lastRun: null,
};

function agentEnv(extra = {}) {
  return {
    ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
    OPENAI_DIGEST_MODEL: process.env.OPENAI_DIGEST_MODEL || 'gpt-5-nano',
    RESEND_API_KEY: process.env.RESEND_API_KEY,
    RESEND_FROM_EMAIL: process.env.RESEND_FROM_EMAIL,
    UNSUBSCRIBE_SECRET: process.env.UNSUBSCRIBE_SECRET,
    TELEGRAM_BOT_TOKEN: process.env.TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID: process.env.TELEGRAM_CHAT_ID,
    TELEGRAM_THREAD_ID: process.env.TELEGRAM_THREAD_ID,
    SITE_URL,
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
  return output;
}

/**
 * news_digest.py prints `TELEMETRY_USAGE={...}` on its own stdout line after a successful
 * Claude call — kept out of digests/data.json (served as-is to the news site) but picked up
 * here and forwarded to telemetry.succeeded() for Zanshin's cost prediction.
 * @returns {{ model?: string, inputTokens?: number, cachedInputTokens?: number, outputTokens?: number } | undefined}
 */
function parseTelemetryUsage(output) {
  const match = output.match(/^TELEMETRY_USAGE=(\{.*\})$/m);
  if (!match) return undefined;
  try {
    return JSON.parse(match[1]);
  } catch {
    return undefined;
  }
}

/**
 * @param {object | null} entry
 * @param {{ changed: boolean, skipped: boolean, skipReason?: string, warnings?: string[], trigger?: string, workChanged?: boolean, workSkipped?: boolean }} context
 */
function buildDigestTelemetry(entry, context) {
  const meta = {
    trigger: context.trigger,
    changed: context.changed,
    skipped: context.skipped,
    workChanged: context.workChanged,
    workSkipped: context.workSkipped,
    siteUrl: SITE_URL,
    warnings: context.warnings?.length ? context.warnings : undefined,
  };

  if (context.skipReason) {
    meta.skipReason = context.skipReason;
  }

  if (entry?.headline) {
    meta.headline = String(entry.headline).slice(0, 200);
    meta.bulletCount = Array.isArray(entry.bullets) ? entry.bullets.length : 0;
    if (entry.timestamp) {
      meta.entryUrl = `${SITE_URL}/entry/${encodeURIComponent(entry.timestamp)}`;
    }
  }

  return meta;
}

/**
 * @template T
 * @param {() => Promise<T>} task
 * @param {{ trigger?: string }} [options]
 * @param {number} [maxRetries]
 * @returns {Promise<T>}
 */
async function runTaskWithTelemetry(task, options = {}, maxRetries = 0) {
  const { trigger } = options;
  await telemetry.started({ trigger });

  const start = Date.now();
  let attempt = 0;

  while (true) {
    try {
      const result = await task();
      const fields =
        typeof result === 'object' && result !== null && 'telemetry' in result
          ? /** @type {{ telemetry: object }} */ (result).telemetry
          : {};

      await telemetry.succeeded(Date.now() - start, { trigger, ...fields });
      return result;
    } catch (err) {
      attempt++;
      if (attempt <= maxRetries) {
        await telemetry.retried();
        continue;
      }

      const message = err instanceof Error ? err.message : String(err);
      await telemetry.failed(Date.now() - start, message, { trigger });
      throw err;
    }
  }
}

/**
 * @param {{ force?: boolean, trigger?: string }} options
 */
async function runExistingDigestTask({ force = false, trigger } = {}) {
  const warnings = [];
  const forceEnv = force ? { FORCE_DIGEST: 'true' } : {};

  await ensureGitRepo();
  await syncLatest();

  const digestOutput = await runPython('news_digest.py', forceEnv);
  const skipped = digestOutput.includes('Digest already exists for today (UTC) — skipping');
  const usage = parseTelemetryUsage(digestOutput);

  let workOutput = '';
  let workSkipped = false;
  try {
    workOutput = await runPython('work_digest.py', forceEnv);
    workSkipped = workOutput.includes('Work digest already exists for today (UTC) — skipping');
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[digest] work_digest.py failed: ${message}`);
    warnings.push(`work_digest.py: ${message}`);
  }

  const workUsage = parseTelemetryUsage(workOutput);
  const commitResult = await commitDigestIfChanged();
  const changed = commitResult.committed;
  const mainChanged = commitResult.mainChanged;
  const workChanged = commitResult.workChanged;

  const bothAlreadyExist =
    skipped && (workSkipped || hasDigestForToday(new Date(), 'work'));
  const skipReason = bothAlreadyExist
    ? 'main and work digests already exist for today (UTC)'
    : skipped && !workSkipped
      ? 'main digest already exists; work digest ran'
      : undefined;

  // Newsletter/Telegram only when the public main digest file changed.
  if (mainChanged) {
    for (const script of ['send_newsletter.py', 'send_telegram.py']) {
      try {
        await runPython(script);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(`[digest] ${script} failed (digest was committed): ${message}`);
        warnings.push(`${script}: ${message}`);
      }
    }
  } else if (skipped) {
    console.log('[digest] Skipping newsletter/Telegram — main digest already exists for today');
  } else {
    console.log('[digest] Skipping newsletter/Telegram — no main digest commit');
  }

  const entry = getLatestDigest('data');
  const telemetryMeta = buildDigestTelemetry(entry, {
    changed,
    skipped: bothAlreadyExist,
    skipReason,
    warnings,
    trigger,
    workChanged,
    workSkipped,
  });

  // Prefer main usage for cost telemetry; fall back to work if main skipped.
  const usageFields = usage || workUsage || {};

  return {
    changed,
    skipped: bothAlreadyExist,
    mainChanged,
    workChanged,
    workSkipped,
    warnings,
    telemetry: { ...telemetryMeta, ...usageFields },
  };
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
    const result = await runTaskWithTelemetry(() => runExistingDigestTask({ force, trigger }), {
      trigger,
    });

    digestState.lastRun = {
      startedAt,
      finishedAt: new Date().toISOString(),
      trigger,
      force,
      changed: result.changed,
      skipped: result.skipped,
      mainChanged: result.mainChanged,
      workChanged: result.workChanged,
      workSkipped: result.workSkipped,
      warnings: result.warnings,
      status: 'success',
      error: null,
    };

    if (result.changed) {
      clearFailureAlertDebounce();
    }

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
      skipped: false,
      warnings: [],
      status: 'error',
      error: message,
    };

    await sendFailureAlert({ trigger, error: message, startedAt }).catch((alertError) => {
      console.error(
        `[digest] Failure alert errored: ${alertError instanceof Error ? alertError.message : alertError}`,
      );
    });

    throw error;
  } finally {
    digestState.running = false;
  }
}
