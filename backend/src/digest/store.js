import fs from 'node:fs';
import path from 'node:path';

import { getRepoRoot } from '../utils/git.js';

function dataPath() {
  return path.join(getRepoRoot(), 'digests', 'data.json');
}

/** @returns {Array<{ timestamp: string, headline: string, bullets: unknown[] }>} */
export function loadDigests() {
  const file = dataPath();
  if (!fs.existsSync(file)) {
    return [];
  }

  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    throw new Error('Failed to read digests/data.json');
  }
}

/** @returns {{ timestamp: string, headline: string, bullets: unknown[] } | null} */
export function getLatestDigest() {
  return loadDigests()[0] ?? null;
}

/** True if the newest local digest entry is from today's UTC date and has real bullets. */
export function hasDigestForToday(now = new Date()) {
  const latest = getLatestDigest();
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

    // Empty/thin digests (e.g. "no major news") don't count — allow catch-up regeneration.
    const bullets = Array.isArray(latest.bullets) ? latest.bullets : [];
    return bullets.length >= 2;
  } catch {
    return false;
  }
}
