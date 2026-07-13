<script setup>
import { computed } from 'vue'
import { useDigestStore } from '@/application/stores/digestStore'
import { useClock } from '@/presentation/composables/useClock'
import { formatUtcClock, formatCountdown } from '@/shared/utils/time'

const store = useDigestStore()
const { now } = useClock()

const clockLabel = computed(() => formatUtcClock(now.value))
const countdownLabel = computed(() =>
  formatCountdown(store.nextRefreshAt, now.value.getTime())
)
</script>

<template>
  <header
    class="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface px-6 py-3.5"
  >
    <RouterLink to="/" class="flex items-center gap-2 font-mono text-[15px] font-semibold tracking-[0.08em]">
      <span
        class="h-2 w-2 flex-shrink-0 rounded-full"
        :class="
          store.hasError
            ? 'bg-error shadow-[0_0_8px_var(--color-error)]'
            : 'animate-pulse-live bg-accent-live shadow-[0_0_8px_var(--color-accent-live)]'
        "
      ></span>
      SIGNAL <span class="text-xs font-normal text-text-muted">/ AI &amp; TECH WIRE</span>
    </RouterLink>
    <div class="font-mono text-xs tracking-[0.04em] text-text-muted">
      <span>{{ clockLabel }}</span>
      <span class="mx-2 opacity-50">·</span>
      <span>NEXT TRANSMISSION {{ countdownLabel }}</span>
    </div>
  </header>
</template>
