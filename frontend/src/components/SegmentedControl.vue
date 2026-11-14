<script setup lang="ts">
defineProps<{
  modelValue: string
  options: { value: string; label: string }[]
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()
</script>

<template>
  <div class="seg">
    <button
      v-for="op in options"
      :key="op.value"
      :class="{ active: modelValue === op.value }"
      @click="emit('update:modelValue', op.value)"
    >
      {{ op.label }}
    </button>
  </div>
</template>

<style lang="scss" scoped>
.seg {
  display: inline-flex;
  gap: 2px;
  background: var(--panel-2);
  padding: 3px;
  border-radius: var(--radius-sm);
  margin-bottom: 1.1rem;
}
button {
  padding: 0.45rem 1.1rem;
  border-radius: 6px;
  font-size: 0.88rem;
  color: var(--ink-2);
  transition: 0.15s;
}
button.active {
  background: var(--panel);
  color: var(--accent);
  font-weight: 600;
  box-shadow: var(--shadow);
}
</style>
