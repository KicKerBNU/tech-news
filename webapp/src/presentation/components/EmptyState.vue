<template>
  <div class="px-5 py-16 text-center">
    <p class="font-mono text-[13px] tracking-[0.1em] text-text-muted">— NO TRANSMISSIONS RECEIVED —</p>
    <p class="mx-auto mt-3 max-w-[420px] font-sans text-[13px] leading-relaxed text-text-muted">
      The agent publishes a new digest daily at 08:00 UTC. Subscribe below to get it in your inbox,
      or check back once GitHub Actions completes its first run.
    </p>
    <div class="mt-8">
      <slot />
    </div>
  </div>
</template>
