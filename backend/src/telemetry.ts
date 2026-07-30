// telemetry.ts — drop-in module, add to the agent's codebase as-is.
const TELEMETRY_BASE_URL = process.env.TELEMETRY_BASE_URL ?? "https://zanshinai-production.up.railway.app";
const TELEMETRY_KEY = process.env.TELEMETRY_INGESTION_KEY!;
const AGENT_API_KEY_ID = process.env.AGENT_API_KEY_ID!;

type TelemetryEventType = "task_started" | "task_succeeded" | "task_failed" | "retried";

type TelemetryFields = {
  durationMs?: number;
  errorMessage?: string;
  trigger?: string;
  changed?: boolean;
  skipped?: boolean;
  skipReason?: string;
  headline?: string;
  bulletCount?: number;
  siteUrl?: string;
  entryUrl?: string;
  warnings?: string[];
  // Real token usage from the Claude call (see news_digest.py's TELEMETRY_USAGE stdout line,
  // parsed by runDigest.js) — unlocks Zanshin's real-time cost prediction for this agent.
  model?: string;
  inputTokens?: number;
  cachedInputTokens?: number;
  outputTokens?: number;
};

async function sendTelemetry(
  eventType: TelemetryEventType,
  fields: TelemetryFields = {},
): Promise<void> {
  if (!TELEMETRY_KEY || !AGENT_API_KEY_ID) {
    return;
  }

  try {
    await fetch(`${TELEMETRY_BASE_URL}/api/telemetry/events`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TELEMETRY_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ apiKeyId: AGENT_API_KEY_ID, eventType, ...fields }),
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    // Telemetry must never break the actual task — swallow and move on.
  }
}

export const telemetry = {
  started: (fields: Omit<TelemetryFields, "durationMs" | "errorMessage"> = {}) =>
    sendTelemetry("task_started", fields),
  succeeded: (durationMs: number, fields: Omit<TelemetryFields, "durationMs" | "errorMessage"> = {}) =>
    sendTelemetry("task_succeeded", { durationMs, ...fields }),
  failed: (
    durationMs: number,
    errorMessage: string,
    fields: Omit<TelemetryFields, "durationMs" | "errorMessage"> = {},
  ) => sendTelemetry("task_failed", { durationMs, errorMessage, ...fields }),
  retried: () => sendTelemetry("retried"),
};
