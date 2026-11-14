<script setup lang="ts">
import { computed } from 'vue'
import type { Citation } from '@/types'

const props = defineProps<{ c: Citation }>()

/** 以 BV 号开头的引用来自 B站，可跳转到对应时间；否则为本地视频，暂不可跳。 */
const isBili = computed(() => /^BV[0-9A-Za-z]{10}/.test(props.c.video_id || ''))

/** 标题兜底：无标题时显示 BV 号或「视频」 */
const title = computed(() => props.c.title || props.c.video_id || '视频')
/** 作者兜底 */
const author = computed(() => props.c.author || '')
/** 完整信息：作者 · 标题 · 分秒，用于移入时 tooltip */
const fullLabel = computed(() =>
  [author.value, title.value, `${fmtMin(props.c.start)}-${fmtMin(props.c.end)}`]
    .filter(Boolean)
    .join(' · '),
)

function fmtMin(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m}分${r}秒` : `${r}秒`
}

function jump() {
  if (!isBili.value || !props.c.video_id) return
  const t = Math.max(0, Math.round(props.c.start))
  window.open(`https://www.bilibili.com/video/${props.c.video_id}/?t=${t}`, '_blank', 'noopener')
}
</script>

<template>
  <span
    class="tag"
    :class="{ clickable: isBili }"
    :title="isBili ? `${fullLabel} — 点击跳转到 B站该时间点` : `${fullLabel} — 本地视频暂不支持跳转`"
    @click="jump"
  >
    {{ author ? `${author} · ${fmtMin(c.start)}-${fmtMin(c.end)}`
             : `${title} · ${fmtMin(c.start)}-${fmtMin(c.end)}` }}
  </span>
</template>

<style lang="scss" scoped>
.tag {
  display: inline-block;
  margin: 0.3rem 0.25rem 0 0;
  font-size: 0.74rem;
  color: var(--accent);
  padding: 0.12rem 0.5rem;
  border-radius: 6px;
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tag.clickable {
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.tag.clickable:hover {
  background: var(--accent-dim);
  color: var(--accent-hover);
}
.tag:not(.clickable) {
  color: var(--ink-3);
}
</style>
