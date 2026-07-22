import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

/**
 * Run a command and return stdout. Throws on non-zero exit with stderr attached.
 */
export async function run(command, args, options = {}) {
  const { cwd, env, label = command } = options;
  try {
    const { stdout, stderr } = await execFileAsync(command, args, {
      cwd,
      env: { ...process.env, ...env },
      maxBuffer: 10 * 1024 * 1024,
    });
    if (stderr?.trim()) {
      console.log(`[${label}] ${stderr.trim()}`);
    }
    return stdout.trim();
  } catch (error) {
    const detail = error.stderr?.trim() || error.message;
    throw new Error(`[${label}] failed: ${detail}`);
  }
}
