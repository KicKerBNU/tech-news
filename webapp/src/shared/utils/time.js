/** e.g. "14:30:07 UTC" — a plain clock display, no domain meaning attached */
export function formatUtcClock(date) {
  return date.toISOString().slice(11, 19) + ' UTC'
}

/** Next occurrence of `hour`:00 UTC (e.g. 08:00 UTC for the daily digest). */
export function getNextDailyUtcAt(hour = 8, now = new Date()) {
  const next = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hour, 0, 0, 0)
  )
  if (next.getTime() <= now.getTime()) {
    next.setUTCDate(next.getUTCDate() + 1)
  }
  return next.getTime()
}

const MONTH_LABELS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

/** e.g. "14 JUL 08:00 UTC" — when the next daily transmission lands */
export function formatNextDailyTransmissionAt(hour = 8, now = new Date()) {
  const next = new Date(getNextDailyUtcAt(hour, now))
  const day = String(next.getUTCDate()).padStart(2, '0')
  const month = MONTH_LABELS[next.getUTCMonth()]
  const time = `${String(hour).padStart(2, '0')}:00 UTC`
  return `${day} ${month} ${time}`
}

/** Countdown string between now and a future timestamp (ms). Includes hours when needed. */
export function formatCountdown(targetMs, nowMs) {
  const totalSeconds = Math.floor(Math.max(0, targetMs - nowMs) / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, '0')
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  if (hours > 0) return `${hours}:${minutes}:${seconds}`
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${seconds}`
}
