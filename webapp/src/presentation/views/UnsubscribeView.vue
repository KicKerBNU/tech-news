<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '@/presentation/components/AppHeader.vue'
import { unsubscribeFromNewsletter } from '@/infrastructure/http/newsletterRepository'

const route = useRoute()
const status = ref('idle') // idle | loading | success | error
const message = ref('')

onMounted(async () => {
  const email = route.query.email
  const sig = route.query.sig
  if (!email || typeof email !== 'string' || !sig || typeof sig !== 'string') {
    status.value = 'error'
    message.value = 'Invalid unsubscribe link.'
    return
  }

  status.value = 'loading'
  try {
    message.value = await unsubscribeFromNewsletter(email, sig)
    status.value = 'success'
  } catch (error) {
    status.value = 'error'
    message.value = error.message
  }
})
</script>

<template>
  <div class="flex min-h-screen flex-col font-sans">
    <AppHeader />

    <main class="mx-auto w-full max-w-[780px] flex-1 px-5 pb-16 pt-12">
      <RouterLink to="/" class="mb-5 inline-block font-mono text-xs text-text-muted hover:text-accent">
        ← back to feed
      </RouterLink>

      <h1 class="font-mono text-lg font-semibold text-text">Unsubscribe</h1>

      <p
        v-if="status === 'loading'"
        class="mt-4 font-mono text-[13px] text-text-muted"
      >
        Processing…
      </p>
      <p
        v-else
        class="mt-4 font-mono text-[13px]"
        :class="status === 'error' ? 'text-error' : 'text-text-muted'"
      >
        {{ message }}
      </p>
    </main>
  </div>
</template>
