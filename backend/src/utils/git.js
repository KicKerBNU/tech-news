import fs from 'node:fs';
import path from 'node:path';

import { run } from './exec.js';

const GIT_MAX_ATTEMPTS = Number(process.env.GIT_MAX_ATTEMPTS || 5);
const GIT_RETRY_BASE_MS = Number(process.env.GIT_RETRY_BASE_MS || 30_000);

export function getRepoRoot() {
  return process.env.REPO_ROOT || path.resolve(import.meta.dirname, '../../..');
}

export function getGitConfig() {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error('GITHUB_TOKEN is required to commit digests back to GitHub');
  }

  return {
    token,
    repo: process.env.GITHUB_REPO || 'KicKerBNU/tech-news',
    branch: process.env.GITHUB_BRANCH || 'master',
  };
}

function remoteUrl(token, repo) {
  // Prefer x-access-token so fine-grained PATs authenticate reliably.
  return `https://x-access-token:${encodeURIComponent(token)}@github.com/${repo}.git`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryableGitError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return /temporarily limiting|rate limit|timed out|TLS|Connection reset|HTTP 5\d\d|unable to access|remote error/i.test(
    message,
  );
}

async function withGitRetries(label, fn) {
  let lastError;
  for (let attempt = 1; attempt <= GIT_MAX_ATTEMPTS; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      const retryable = isRetryableGitError(error);
      if (!retryable || attempt === GIT_MAX_ATTEMPTS) {
        throw error;
      }

      const waitMs = GIT_RETRY_BASE_MS * attempt;
      console.warn(
        `[git] ${label} failed (attempt ${attempt}/${GIT_MAX_ATTEMPTS}): ${
          error instanceof Error ? error.message : error
        } — retrying in ${Math.round(waitMs / 1000)}s`,
      );
      await sleep(waitMs);
    }
  }

  throw lastError;
}

async function configureAuth(repoRoot) {
  const { token, repo } = getGitConfig();
  const url = remoteUrl(token, repo);

  // Avoid credential helpers stripping the token from the remote URL.
  await run('git', ['config', 'credential.helper', ''], { cwd: repoRoot, label: 'git' });
  await run('git', ['remote', 'set-url', 'origin', url], { cwd: repoRoot, label: 'git' });
  await run('git', ['config', 'user.name', 'signal-digest-bot'], { cwd: repoRoot, label: 'git' });
  await run('git', ['config', 'user.email', 'digest@signal-news-agent'], { cwd: repoRoot, label: 'git' });
}

export async function ensureGitRepo() {
  const repoRoot = getRepoRoot();
  const { token, repo, branch } = getGitConfig();
  const url = remoteUrl(token, repo);
  const gitDir = path.join(repoRoot, '.git');

  fs.mkdirSync(repoRoot, { recursive: true });

  if (!fs.existsSync(gitDir)) {
    console.log('[git] Cloning repository from GitHub…');
    const hasFiles = fs.readdirSync(repoRoot).length > 0;
    if (hasFiles) {
      throw new Error(`[git] ${repoRoot} is not empty — cannot clone`);
    }

    await withGitRetries('clone', async () => {
      await run('git', ['clone', '--branch', branch, '--single-branch', url, repoRoot], {
        cwd: path.dirname(repoRoot),
        label: 'git',
      });
    });
  }

  await configureAuth(repoRoot);
}

export async function syncLatest() {
  const repoRoot = getRepoRoot();
  const { branch } = getGitConfig();

  await configureAuth(repoRoot);

  await withGitRetries('sync', async () => {
    await run('git', ['fetch', 'origin', branch], { cwd: repoRoot, label: 'git' });
    await run('git', ['checkout', branch], { cwd: repoRoot, label: 'git' });
    await run('git', ['pull', '--rebase', 'origin', branch], { cwd: repoRoot, label: 'git' });
  });
}

/** @returns {Promise<boolean>} true if a commit was pushed */
export async function commitDigestIfChanged() {
  const repoRoot = getRepoRoot();
  const dataPath = 'digests/data.json';
  const { branch } = getGitConfig();

  await configureAuth(repoRoot);
  await run('git', ['add', dataPath], { cwd: repoRoot, label: 'git' });

  try {
    await run('git', ['diff', '--staged', '--quiet'], { cwd: repoRoot, label: 'git' });
    console.log('[git] No digest changes to commit');
    return false;
  } catch {
    const timestamp = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
    await run('git', ['commit', '-m', `digest: ${timestamp}`], { cwd: repoRoot, label: 'git' });
    await withGitRetries('push', async () => {
      await run('git', ['push', 'origin', branch], { cwd: repoRoot, label: 'git' });
    });
    console.log('[git] Pushed new digest commit');
    return true;
  }
}
