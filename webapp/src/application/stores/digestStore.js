import { defineStore } from 'pinia'
import { createGithubDigestRepository } from '@/infrastructure/http/githubDigestRepository'
import { getNextDailyUtcAt } from '@/shared/utils/time'

export const DAILY_UPDATE_HOUR_UTC = 8 // matches backend CRON_SCHEDULE (default 08:00 UTC)
export const REFRESH_INTERVAL_MS = 30 * 60 * 1000 // poll every 30 min to catch the daily drop

const repository = createGithubDigestRepository()

export const useDigestStore = defineStore('digest', {
  state: () => ({
    entries: /** @type {import('@/domain/digest/DigestEntry').DigestEntry[]} */ ([]),
    status: 'idle', // 'idle' | 'loading' | 'ready' | 'error'
    lastFetchedAt: /** @type {Date|null} */ (null),
    nextRefreshAt: getNextDailyUtcAt(DAILY_UPDATE_HOUR_UTC),
  }),

  getters: {
    latestEntry: (state) => state.entries[0] ?? null,
    hasEntries: (state) => state.entries.length > 0,
    hasError: (state) => state.status === 'error',
  },

  actions: {
    async fetchEntries() {
      this.status = 'loading'
      try {
        this.entries = await repository.fetchAll()
        this.status = 'ready'
      } catch (error) {
        this.status = 'error'
      } finally {
        this.lastFetchedAt = new Date()
        this.nextRefreshAt = getNextDailyUtcAt(DAILY_UPDATE_HOUR_UTC)
      }
    },

    findById(id) {
      return this.entries.find((entry) => entry.id === id) ?? null
    },
  },
})
