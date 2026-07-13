/**
 * DigestEntry — domain entity for one wire transmission.
 * Knows nothing about HTTP, Vue, or where the data came from.
 */
export class DigestEntry {
  constructor({ timestamp, headline, bullets = [] }) {
    this.timestamp = timestamp
    this.headline = headline
    this.bullets = bullets
  }

  /** Stable identity for routing / list keys */
  get id() {
    return this.timestamp
  }

  /** e.g. "2026-07-13 14:30" — the wire-stamp format used throughout the UI */
  get stamp() {
    return new Date(this.timestamp).toISOString().slice(0, 16).replace('T', ' ')
  }

  /** e.g. "12m ago" — freshness is a domain concept (relevant to a news feed) */
  get relativeAge() {
    const diffMin = Math.round((Date.now() - new Date(this.timestamp).getTime()) / 60000)
    if (diffMin < 1) return 'just now'
    if (diffMin < 60) return `${diffMin}m ago`
    return `${Math.round(diffMin / 60)}h ago`
  }

  static fromJSON(json) {
    return new DigestEntry(json)
  }
}
