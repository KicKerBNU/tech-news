/**
 * Sends one task_started event and prints the HTTP status/body (for debugging).
 * Usage: TELEMETRY_INGESTION_KEY=... AGENT_API_KEY_ID=... yarn verify:telemetry
 */
const TELEMETRY_BASE_URL = process.env.TELEMETRY_BASE_URL ?? 'https://zanshinai-production.up.railway.app';
const TELEMETRY_KEY = process.env.TELEMETRY_INGESTION_KEY;
const AGENT_API_KEY_ID = process.env.AGENT_API_KEY_ID;

if (!TELEMETRY_KEY || !AGENT_API_KEY_ID) {
  console.error('Missing TELEMETRY_INGESTION_KEY or AGENT_API_KEY_ID');
  process.exit(1);
}

const response = await fetch(`${TELEMETRY_BASE_URL}/api/telemetry/events`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${TELEMETRY_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ apiKeyId: AGENT_API_KEY_ID, eventType: 'task_started' }),
  signal: AbortSignal.timeout(5000),
});

const body = await response.text();
console.log(`HTTP ${response.status}`);
console.log(body || '(empty body)');

if (!response.ok) {
  process.exit(1);
}
