import fs from 'node:fs';
import path from 'node:path';

import { getRepoRoot } from '../utils/git.js';

/** @typedef {'data' | 'work'} DigestKind */

const DIGEST_FILES = {
  data: 'data.json',
  work: 'work.json',
};

/**
 * @param {DigestKind} [kind]
 */
function digestPath(kind = 'data') {
  const file = DIGEST_FILES[kind] || DIGEST_FILES.data;
  return path.join(getRepoRoot(), 'digests', file);
}

/**
 * @param {DigestKind} [kind]
 * @returns {Array<{ timestamp: string, headline: string, bullets: unknown[] }>}
 */
export function loadDigests(kind = 'data') {
  const file = digestPath(kind);
  if (!fs.existsSync(file)) {
    return [];
  }

  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    throw new Error(`Failed to read digests/${DIGEST_FILES[kind] || 'data.json'}`);
  }
}

/**
 * @param {DigestKind} [kind]
 * @returns {{ timestamp: string, headline: string, bullets: unknown[] } | null}
 */
export function getLatestDigest(kind = 'data') {
  return loadDigests(kind)[0] ?? null;
}

/**
 * True if the newest local digest entry is from today's UTC date and has real bullets.
 * @param {Date} [now]
 * @param {DigestKind} [kind]
 */
export function hasDigestForToday(now = new Date(), kind = 'data') {
  const latest = getLatestDigest(kind);
  if (!latest?.timestamp) {
    return false;
  }

  try {
    const dt = new Date(latest.timestamp);
    if (Number.isNaN(dt.getTime())) {
      return false;
    }

    const today = now.toISOString().slice(0, 10);
    if (dt.toISOString().slice(0, 10) !== today) {
      return false;
    }

    const bullets = Array.isArray(latest.bullets) ? latest.bullets : [];
    return bullets.length >= 2;
  } catch {
    return false;
  }
}

/** True when both the main and work digests exist for today's UTC date. */
export function hasAllDigestsForToday(now = new Date()) {
  return hasDigestForToday(now, 'data') && hasDigestForToday(now, 'work');
}
