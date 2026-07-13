<script setup>
import { computed, onMounted } from 'vue'
import { useDigestStore } from '@/application/stores/digestStore'
import AppHeader from '@/presentation/components/AppHeader.vue'
import DigestCard from '@/presentation/components/DigestCard.vue'

const props = defineProps({
  id: { type: String, required: true },
})

const store = useDigestStore()

onMounted(() => {
  if (!store.hasEntries) store.fetchEntries()
})

const entry = computed(() => store.findById(props.id))
</script>

<template>
  <div class="flex min-h-screen flex-col font-sans">
    <AppHeader />

    <main class="mx-auto w-full max-w-[780px] flex-1 px-5 pb-16 pt-8">
      <RouterLink to="/" class="mb-5 inline-block font-mono text-xs text-text-muted hover:text-accent">
        ← back to feed
      </RouterLink>

      <DigestCard v-if="entry" :entry="entry" />
      <p v-else class="font-mono text-[13px] text-text-muted">
        Transmission not found — it may have rolled off the feed, or hasn't loaded yet.
      </p>
    </main>
  </div>
</template>
