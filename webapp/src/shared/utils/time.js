/** e.g. "14:30:07 UTC" — a plain clock display, no domain meaning attached */
export function formatUtcClock(date) {
  return date.toISOString().slice(11, 19) + ' UTC'
}

/** mm:ss countdown string between now and a future timestamp (ms) */
export function formatCountdown(targetMs, nowMs) {
  const totalSeconds = Math.floor(Math.max(0, targetMs - nowMs) / 1000)
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0')
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}
