import { defineStore } from 'pinia'
import { createGithubDigestRepository } from '@/infrastructure/http/githubDigestRepository'

export const REFRESH_INTERVAL_MS = 10 * 60 * 1000 // matches the agent's cadence

const repository = createGithubDigestRepository()

export const useDigestStore = defineStore('digest', {
  state: () => ({
    entries: /** @type {import('@/domain/digest/DigestEntry').DigestEntry[]} */ ([]),
    status: 'idle', // 'idle' | 'loading' | 'ready' | 'error'
    lastFetchedAt: /** @type {Date|null} */ (null),
    nextRefreshAt: Date.now() + REFRESH_INTERVAL_MS,
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
        this.nextRefreshAt = Date.now() + REFRESH_INTERVAL_MS
      }
    },

    findById(id) {
      return this.entries.find((entry) => entry.id === id) ?? null
    },
  },
})
