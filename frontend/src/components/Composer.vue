<script setup lang="ts">
import { Button } from '@/components/ui/button'
import Textarea from '@/components/ui/textarea/Textarea.vue'
import { ArrowUp } from '@lucide/vue'
import { ref, watch } from 'vue'

const props = defineProps<{ disabled: boolean; placeholder?: string }>()
const emit = defineEmits<{ (e: 'send', text: string): void }>()

const text = defineModel<string>({ default: '' })
const el = ref<InstanceType<typeof Textarea> | null>(null)

/** 随内容自动增高，最多约 4 行，超出后内部滚动 */
function autosize() {
  const t = el.value?.element
  if (!t) return
  t.style.height = 'auto'
  t.style.height = `${Math.min(t.scrollHeight, 132)}px`
}

watch(text, autosize, { flush: 'post' })

function send() {
  const v = (text.value || '').trim()
  if (!v || props.disabled) return
  text.value = ''
  emit('send', v)
}

function onEnter(event: KeyboardEvent) {
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  send()
}
</script>

<template>
  <div class="composer">
    <Textarea
      ref="el"
      class="quiet-scroll"
      v-model="text"
      rows="1"
      :placeholder="placeholder || '输入你的问题…'"
      aria-label="输入你的问题"
      @input="autosize"
      @keydown.enter.exact="onEnter"
    />
    <Button class="send" size="icon" type="button" :disabled="disabled || !text?.trim()" aria-label="发送" @click="send">
      <ArrowUp class="size-[19px]" :stroke-width="2.5" aria-hidden="true" />
    </Button>
  </div>
</template>

<style lang="scss" scoped>
.composer {
  flex: none;
  display: flex;
  gap: 0.7rem;
  align-items: end;
  border: 1px solid var(--line-strong);
  border-radius: 16px;
  background: var(--panel);
  padding: .4rem;
}
.composer:focus-within {
  border-color: var(--accent-line);
  box-shadow: 0 0 0 2px var(--accent-dim);
}
textarea {
  flex: 1;
  min-width: 0;
  resize: none;
  padding: 0.55rem 0.65rem;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: 1rem;
  line-height: 1.5;
  outline: none;
  box-shadow: none;
  min-height: 40px;
  max-height: 132px;
  overflow-y: auto;
}
.send {
  width: 36px;
  height: 36px;
  flex: none;
  margin: 2px;
  border-radius: 9px;
  background: var(--panel);
  border: 1px solid var(--line-strong);
  color: var(--accent);
  display: grid;
  place-items: center;
  transition: 0.15s;
}
.send:hover:not(:disabled) {
  background: var(--panel);
  border-color: var(--accent);
}
.send:disabled {
  opacity: 1;
  background: var(--panel);
  border-color: var(--line);
  cursor: not-allowed;
}
.send svg {
  width: 19px;
  height: 19px;
}
</style>
