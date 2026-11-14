<script setup lang="ts">
import { ref } from 'vue'
import { ScrollAreaRoot, ScrollAreaScrollbar, ScrollAreaThumb, ScrollAreaViewport } from 'reka-ui'

defineProps<{ label: string }>()
defineEmits<{ scroll: [] }>()

const viewport = ref<InstanceType<typeof ScrollAreaViewport> | null>(null)
defineExpose({ getViewport: () => viewport.value?.viewportElement })
</script>

<template>
  <ScrollAreaRoot class="scroll-area" type="scroll" :scroll-hide-delay="350">
    <ScrollAreaViewport
      ref="viewport"
      class="viewport"
      style="overflow-y: auto"
      role="region"
      :aria-label="label"
      @scroll.passive="$emit('scroll')"
    >
      <slot />
    </ScrollAreaViewport>
    <ScrollAreaScrollbar orientation="vertical" class="scrollbar">
      <ScrollAreaThumb class="thumb" />
    </ScrollAreaScrollbar>
  </ScrollAreaRoot>
</template>

<style scoped>
.scroll-area { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }
.viewport { flex: 1 1 auto; min-height: 0; width: 100%; overscroll-behavior: contain; }
.viewport:focus-visible { outline-offset: -2px; }
.scrollbar { display: flex; width: 10px; padding: 0 2px; touch-action: none; user-select: none; }
.thumb { position: relative; flex: 1; border-radius: 999px; background: #a4adb7; }
</style>
