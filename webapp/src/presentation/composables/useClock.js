import { ref, onMounted, onUnmounted } from 'vue'

/** Reactive "now", ticking every `intervalMs`. Cleans up after itself. */
export function useClock(intervalMs = 1000) {
  const now = ref(new Date())
  let timer

  onMounted(() => {
    timer = setInterval(() => {
      now.value = new Date()
    }, intervalMs)
  })
  onUnmounted(() => clearInterval(timer))

  return { now }
}
