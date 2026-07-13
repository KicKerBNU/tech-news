import { DigestEntry } from '@/domain/digest/DigestEntry'

const DEFAULT_DATA_URL =
  'https://raw.githubusercontent.com/KicKerBNU/tech-news/main/digests/data.json'

/**
 * Repository for digest entries, backed by a raw file on GitHub's CDN.
 * Everything above this layer (store, views) only knows "fetchAll() -> DigestEntry[]",
 * not that it happens to be a raw GitHub URL — swap this file alone if the
 * data source ever changes (a real API, etc.) and nothing else needs to move.
 */
export function createGithubDigestRepository(dataUrl = DEFAULT_DATA_URL) {
  return {
    async fetchAll() {
      const response = await fetch(`${dataUrl}?t=${Date.now()}`) // cache-bust the CDN
      if (!response.ok) {
        throw new Error(`Failed to fetch digest data (${response.status})`)
      }
      const raw = await response.json()
      return raw.map(DigestEntry.fromJSON)
    },
  }
}
