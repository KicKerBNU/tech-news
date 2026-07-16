<script setup>
import { ref } from 'vue'
import { subscribeToNewsletter } from '@/infrastructure/http/newsletterRepository'

defineProps({
  variant: {
    type: String,
    default: 'hero', // hero | embedded
  },
})

const email = ref('')
const status = ref('idle') // idle | loading | success | error
const message = ref('')

async function onSubmit() {
  if (!email.value.trim()) return

  status.value = 'loading'
  message.value = ''

  try {
    message.value = await subscribeToNewsletter(email.value.trim())
    status.value = 'success'
    email.value = ''
  } catch (error) {
    status.value = 'error'
    message.value = error.message
  }
}
</script>

<template>
  <section
    class="relative overflow-hidden border border-border bg-surface-2"
    :class="variant === 'embedded' ? 'mx-auto max-w-[520px]' : 'w-full'"
  >
    <div
      class="pointer-events-none absolute inset-0 bg-gradient-to-br from-accent/[0.07] via-transparent to-transparent"
      aria-hidden="true"
    />
    <div
      class="absolute bottom-0 left-0 top-0 w-0.5 bg-accent"
      aria-hidden="true"
    />

    <div class="relative px-5 py-6 sm:px-7 sm:py-7">
      <div class="flex items-start gap-3">
        <span
          class="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full shadow-[0_0_8px_var(--color-accent-live)]"
          :class="status === 'success' ? 'bg-accent-live' : 'animate-pulse-live bg-accent-live'"
          aria-hidden="true"
        />

        <div class="min-w-0 flex-1">
          <p class="font-mono text-[10px] tracking-[0.14em] text-accent">INBOX TRANSMISSION</p>
          <h2 class="mt-1.5 font-mono text-[17px] font-semibold leading-snug text-text sm:text-lg">
            Get the daily wire in your email
          </h2>
          <p class="mt-2 font-sans text-[13px] leading-relaxed text-text-muted">
            AI &amp; tech digest every morning at 08:00 UTC. No account — just your address.
          </p>

          <div
            v-if="status === 'success'"
            class="mt-5 rounded border border-accent/30 bg-accent/[0.08] px-4 py-3"
          >
            <p class="font-mono text-[12px] leading-relaxed text-accent-live">
              ✓ {{ message }}
            </p>
          </div>

          <form
            v-else
            class="mt-5"
            @submit.prevent="onSubmit"
          >
            <label for="newsletter-email" class="mb-2 block font-mono text-[10px] tracking-[0.1em] text-text-muted">
              EMAIL ADDRESS
            </label>
            <div class="flex flex-col gap-2.5 sm:flex-row sm:items-stretch">
              <input
                id="newsletter-email"
                v-model="email"
                type="email"
                name="email"
                autocomplete="email"
                placeholder="you@example.com"
                :disabled="status === 'loading'"
                class="min-w-0 flex-1 rounded border border-border bg-bg px-3.5 py-3 font-mono text-sm text-text outline-none transition placeholder:text-text-muted/70 focus:border-accent focus:shadow-[0_0_0_1px_var(--color-accent)] disabled:opacity-60"
              />
              <button
                type="submit"
                :disabled="status === 'loading' || !email.trim()"
                class="rounded border border-accent bg-accent px-5 py-3 font-mono text-[11px] font-semibold tracking-[0.1em] text-bg transition hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50 sm:min-w-[140px]"
              >
                {{ status === 'loading' ? 'SENDING…' : 'SUBSCRIBE' }}
              </button>
            </div>

            <p
              v-if="status === 'error'"
              class="mt-3 font-mono text-[12px] leading-relaxed text-error"
            >
              {{ message }}
            </p>
          </form>

          <p class="mt-4 font-mono text-[10px] leading-relaxed text-text-muted/80">
            Unsubscribe anytime · one email per day
          </p>
        </div>
      </div>
    </div>
  </section>
</template>
