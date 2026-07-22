import fs from 'node:fs';
import path from 'node:path';

import { run } from './exec.js';

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
  return `https://x-access-token:${token}@github.com/${repo}.git`;
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
    await run('git', ['clone', '--branch', branch, '--single-branch', url, repoRoot], {
      cwd: path.dirname(repoRoot),
      label: 'git',
    });
  } else {
    await run('git', ['remote', 'set-url', 'origin', url], { cwd: repoRoot, label: 'git' });
  }

  await run('git', ['config', 'user.name', 'signal-digest-bot'], { cwd: repoRoot, label: 'git' });
  await run('git', ['config', 'user.email', 'digest@signal-news-agent'], { cwd: repoRoot, label: 'git' });
}

export async function syncLatest() {
  const repoRoot = getRepoRoot();
  const { branch } = getGitConfig();

  await run('git', ['fetch', 'origin', branch], { cwd: repoRoot, label: 'git' });
  await run('git', ['checkout', branch], { cwd: repoRoot, label: 'git' });
  await run('git', ['pull', '--rebase', 'origin', branch], { cwd: repoRoot, label: 'git' });
}

/** @returns {Promise<boolean>} true if a commit was pushed */
export async function commitDigestIfChanged() {
  const repoRoot = getRepoRoot();
  const dataPath = 'digests/data.json';

  await run('git', ['add', dataPath], { cwd: repoRoot, label: 'git' });

  try {
    await run('git', ['diff', '--staged', '--quiet'], { cwd: repoRoot, label: 'git' });
    console.log('[git] No digest changes to commit');
    return false;
  } catch {
    const timestamp = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
    await run('git', ['commit', '-m', `digest: ${timestamp}`], { cwd: repoRoot, label: 'git' });
    await run('git', ['push', 'origin', getGitConfig().branch], { cwd: repoRoot, label: 'git' });
    console.log('[git] Pushed new digest commit');
    return true;
  }
}
