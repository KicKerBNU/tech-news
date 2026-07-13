<script setup>
import { computed } from 'vue'
import { useDigestStore, REFRESH_INTERVAL_MS } from '@/application/stores/digestStore'
import { usePolling } from '@/presentation/composables/usePolling'
import { useClock } from '@/presentation/composables/useClock'
import { formatUtcClock } from '@/shared/utils/time'
import AppHeader from '@/presentation/components/AppHeader.vue'
import DigestCard from '@/presentation/components/DigestCard.vue'
import EmptyState from '@/presentation/components/EmptyState.vue'

const store = useDigestStore()
const { now } = useClock()

usePolling(() => store.fetchEntries(), REFRESH_INTERVAL_MS)

const lastSyncedLabel = computed(() =>
  store.lastFetchedAt ? formatUtcClock(store.lastFetchedAt) : null
)
</script>

<template>
  <div class="flex min-h-screen flex-col font-sans">
    <AppHeader />

    <main class="mx-auto w-full max-w-[780px] flex-1 px-5 pb-16 pt-8">
      <p
        v-if="store.status === 'loading' && !store.hasEntries"
        class="px-5 py-20 text-center font-mono text-[13px] tracking-[0.1em] text-text-muted"
      >
        — SYNCING TRANSMISSIONS —
      </p>

      <EmptyState v-else-if="store.status === 'ready' && !store.hasEntries" />

      <RouterLink
        v-for="(entry, i) in store.entries"
        :key="entry.id"
        :to="{ name: 'entry-detail', params: { id: entry.id } }"
        class="block"
      >
        <DigestCard :entry="entry" :highlighted="i === 0" />
      </RouterLink>
    </main>

    <footer class="border-t border-border px-4 py-4 text-center font-mono text-[11px] text-text-muted">
      <span>Updated daily at 08:00 UTC</span>
      <span v-if="lastSyncedLabel"> · last synced {{ lastSyncedLabel }}</span>
      <span v-if="store.hasError" class="text-error"> · sync failed, retrying next cycle</span>
    </footer>
  </div>
</template>
