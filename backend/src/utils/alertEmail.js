/**
 * Failure alerts via Resend — sent from Node so git/Claude failures still notify.
 * Debounced to one alert per UTC day (catch-up retries won't spam).
 */

const RESEND_API = 'https://api.resend.com';

/** @type {string | null} */
let lastFailureAlertDay = null;

function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

/**
 * @param {{ trigger?: string, error: string, startedAt?: string, force?: boolean }} details
 * @returns {Promise<{ sent: boolean, reason?: string }>}
 */
export async function sendFailureAlert(details) {
  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.RESEND_FROM_EMAIL;
  const to = process.env.ALERT_EMAIL;

  const missing = [
    !apiKey && 'RESEND_API_KEY',
    !from && 'RESEND_FROM_EMAIL',
    !to && 'ALERT_EMAIL',
  ].filter(Boolean);

  if (missing.length) {
    console.warn(`[alert] Skipping failure email — missing: ${missing.join(', ')}`);
    return { sent: false, reason: 'missing_config', missing };
  }

  const day = todayUtc();
  if (!details.force && lastFailureAlertDay === day) {
    console.log(`[alert] Failure alert already sent for ${day} — skipping`);
    return { sent: false, reason: 'already_sent_today' };
  }

  const when = details.startedAt || new Date().toISOString();
  const trigger = details.trigger || 'unknown';
  const error = details.error || 'Unknown error';
  const siteUrl = (process.env.SITE_URL || 'https://signal-news-agent.netlify.app').replace(/\/$/, '');
  const healthUrl = process.env.RAILWAY_PUBLIC_URL
    ? `${process.env.RAILWAY_PUBLIC_URL.replace(/\/$/, '')}/health`
    : 'https://tech-news-production-af46.up.railway.app/health';

  const subject = `SIGNAL digest FAILED (${day})`;
  const html = `
    <div style="font-family: ui-sans-serif, system-ui, sans-serif; line-height: 1.5; color: #111;">
      <h2 style="margin: 0 0 12px;">SIGNAL digest failed</h2>
      <p style="margin: 0 0 8px;">The daily tech-news job did not complete successfully.</p>
      <table style="border-collapse: collapse; margin: 16px 0;">
        <tr><td style="padding: 4px 12px 4px 0; color: #666;">When (UTC)</td><td>${escapeHtml(when)}</td></tr>
        <tr><td style="padding: 4px 12px 4px 0; color: #666;">Trigger</td><td>${escapeHtml(trigger)}</td></tr>
        <tr><td style="padding: 4px 12px 4px 0; color: #666;">Error</td><td><code style="white-space: pre-wrap;">${escapeHtml(error)}</code></td></tr>
      </table>
      <p style="margin: 0 0 8px;">Catch-up retries run every 5 minutes until today's digest exists.</p>
      <p style="margin: 0;">
        <a href="${escapeHtml(healthUrl)}">Check /health</a>
        ·
        <a href="${escapeHtml(siteUrl)}">Open site</a>
      </p>
    </div>
  `;

  try {
    const response = await fetch(`${RESEND_API}/emails`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'User-Agent': 'signal-news-agent/1.0',
      },
      body: JSON.stringify({
        from,
        to: [to],
        subject,
        html,
      }),
      signal: AbortSignal.timeout(15_000),
    });

    const body = await response.text();
    if (!response.ok) {
      console.error(`[alert] Resend error (${response.status}): ${body}`);
      return { sent: false, reason: `http_${response.status}` };
    }

    lastFailureAlertDay = day;
    console.log(`[alert] Failure email sent to ${to}`);
    return { sent: true };
  } catch (error) {
    console.error(`[alert] Failed to send failure email: ${error instanceof Error ? error.message : error}`);
    return { sent: false, reason: 'send_failed' };
  }
}

/** Reset debounce after a successful digest (allows a new alert later the same day if needed). */
export function clearFailureAlertDebounce() {
  lastFailureAlertDay = null;
}
