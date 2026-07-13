<script setup>
defineProps({
  entry: { type: Object, required: true }, // DigestEntry
  highlighted: { type: Boolean, default: false },
})
</script>

<template>
  <article
    class="flex flex-col gap-1.5 border-b border-border py-5 sm:flex-row sm:gap-4"
    :class="
      highlighted
        ? 'border-l-2 border-l-accent bg-gradient-to-r from-accent/[0.06] to-transparent pl-4 sm:-ml-[18px]'
        : ''
    "
  >
    <div
      class="flex gap-2.5 font-mono text-[11px] leading-relaxed text-text-muted sm:block sm:w-[100px] sm:flex-shrink-0 sm:pt-[3px]"
    >
      <div class="whitespace-nowrap">{{ entry.stamp }}</div>
      <div class="text-accent sm:mt-0.5">{{ entry.relativeAge }}</div>
    </div>
    <div>
      <h2 class="mb-2.5 font-mono text-base font-semibold leading-snug text-text">{{ entry.headline }}</h2>
      <ul class="flex flex-col gap-2">
        <li v-for="(bullet, i) in entry.bullets" :key="i" class="text-[13.5px] leading-relaxed text-text">
          <span class="font-medium">{{ bullet.title }}</span>
          <span class="text-text-muted"> — {{ bullet.summary }}</span>
          <span class="ml-1 font-mono text-[11px] text-accent">[{{ bullet.source }}]</span>
        </li>
      </ul>
    </div>
  </article>
</template>
