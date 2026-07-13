import { onMounted, onUnmounted } from 'vue'

/** Fires `callback` once immediately, then every `intervalMs`. */
export function usePolling(callback, intervalMs) {
  let timer

  onMounted(() => {
    callback()
    timer = setInterval(callback, intervalMs)
  })
  onUnmounted(() => clearInterval(timer))
}
