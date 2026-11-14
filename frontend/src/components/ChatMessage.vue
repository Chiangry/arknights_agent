<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { ChatMessage, Citation } from '@/types'
import { renderMarkdown } from '@/utils/markdown'
import CitationTag from '@/components/CitationTag.vue'
import AudioImportOffer from '@/components/AudioImportOffer.vue'

const props = defineProps<{ m: ChatMessage }>()

function fmtMin(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m}分${r}秒` : `${r}秒`
}

function fmtPlay(play: number): string {
  return play >= 10000 ? `${(play / 10000).toFixed(play >= 100000 ? 0 : 1)}万播放` : `${play} 播放`
}

function stepIcon(status: string): string {
  return ({ running: '…', completed: '✓', warning: '!', failed: '×' } as Record<string, string>)[status] || '·'
}

function stepLabel(stage: string): string {
  return ({
    knowledge_search: '知识库检索', answer_check: '片段核验', bilibili_search: 'B站搜索',
    external_subtitles: '字幕检索', answer: '生成回答', answer_review: '答案复核',
    external_answer: '综合回答', external_review: '综合复核',
    external_audio_1: '音频处理', external_audio_2: '音频处理',
    external_audio_reuse: '转写复用',
    game_state: '对局状态',
  } as Record<string, string>)[stage] || stage
}

/** 只有 B 站视频能跳到对应时间点 */
function refUrl(c: Citation): string | null {
  const vid = c.video_id || ''
  if (!/^BV[0-9A-Za-z]{10}/.test(vid)) return null
  return `https://www.bilibili.com/video/${vid}/?t=${Math.max(0, Math.round(c.start))}`
}

/** 段落角标的悬浮说明 */
function refLabel(c: Citation): string {
  return [c.author, c.title || c.video_id, `${fmtMin(c.start)}-${fmtMin(c.end)}`]
    .filter(Boolean)
    .join(' · ')
}

/* ---------- 角标悬浮卡片 ---------- */
const tip = ref<{ i: number; x: number; y: number } | null>(null)
const tipEl = ref<HTMLElement | null>(null)
let enterTimer: number | undefined
let leaveTimer: number | undefined

const tipCite = computed<Citation | null>(() =>
  tip.value ? props.m.citations[tip.value.i - 1] || null : null,
)

function cancelTimers() {
  window.clearTimeout(enterTimer)
  window.clearTimeout(leaveTimer)
}

function onBodyOver(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest?.('a.cite') as HTMLElement | null
  if (!el) return
  const i = Number(el.dataset.ref)
  if (!i) return
  window.clearTimeout(leaveTimer)
  window.clearTimeout(enterTimer)
  enterTimer = window.setTimeout(() => void showTip(el, i), 80)
}

function onBodyOut(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest?.('a.cite') as HTMLElement | null
  if (!el) return
  window.clearTimeout(enterTimer)
  leaveTimer = window.setTimeout(() => (tip.value = null), 140)
}

/** 定位：优先弹在角标上方，上方空间不够时落到下方，左右夹在视口内 */
async function showTip(el: HTMLElement, i: number) {
  const r = el.getBoundingClientRect()
  const width = Math.min(272, window.innerWidth - 20)
  const x = Math.min(Math.max(10, r.left - 6), window.innerWidth - width - 10)
  tip.value = { i, x, y: r.top }
  await nextTick()
  const h = tipEl.value?.offsetHeight || 96
  const above = r.top - h - 10 > 8
  tip.value = { i, x, y: above ? r.top - h - 10 : r.bottom + 10 }
}

function holdTip() {
  window.clearTimeout(leaveTimer)
}

function hideTip() {
  window.clearTimeout(enterTimer)
  tip.value = null
}

/** 页面一旦滚动，固定定位的卡片就跟不上了，直接收起 */
function onScroll() {
  tip.value = null
}

onMounted(() => window.addEventListener('scroll', onScroll, true))
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll, true)
  cancelTimers()
})

/** 属性值转义，避免来源标题里的引号破坏 HTML */
function escAttr(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 渲染助手正文：
 * 回答正文里的 [引用N] 转成文字后上标的小数字角标（常见问答产品的脚注样式），
 * 位置保持原文所在处 —— 通常在句末/段末，就显示在那句话的右上角。
 * 解析顺序：先把 [引用N] 换成占位标记 → markdown 渲染 → 占位替换为角标 HTML。
 */
const html = computed(() => {
  const m = props.m
  if (!m.citations.length) return renderMarkdown(m.text)

  const withMarks = m.text.replace(/[ \t]*\[引用(\d+)\][ \t]*/g, (all, n, offset, str) => {
    const before = str[offset - 1] || ''
    const after = str[offset + all.length] || ''
    // 英文/数字相邻时补一个空格，中文直接删掉
    const sep = /[A-Za-z0-9]/.test(before) && /[A-Za-z0-9]/.test(after) ? ' ' : ''
    return `⟦R${n}⟧${sep}`
  })

  return renderMarkdown(withMarks).replace(/⟦R(\d+)⟧/g, (_, n) => {
    const i = Number(n)
    const c = m.citations[i - 1]
    if (!c) return ''
    const url = refUrl(c)
    const label = escAttr(refLabel(c))
    const attrs = url ? ` href="${url}" target="_blank" rel="noopener"` : ' href="#"'
    // 不用原生 title，改用自定义悬浮卡片（见下方 cite-tip）
    return `<a class="cite" data-ref="${i}"${attrs} aria-label="${label}">${i}</a>`
  })
})
</script>

<template>
  <div class="msg" :class="m.role">
    <template v-if="m.role === 'a'">
      <span class="who">视知助手</span>
      <details v-if="m.agentSteps?.length" class="agent-trace" :open="m.streaming">
        <summary class="trace-title">{{ m.streaming ? '正在处理 · 检索过程' : '查看检索过程' }}</summary>
        <div v-for="step in m.agentSteps" :key="step.stage" class="trace-step" :class="step.status">
          <span class="trace-icon">{{ stepIcon(step.status) }}</span>
          <strong>{{ stepLabel(step.stage) }}</strong>
          <span>{{ step.message }}</span>
        </div>
      </details>
      <div
        class="body markdown"
        v-html="html"
        @mouseover="onBodyOver"
        @mouseout="onBodyOut"
      ></div>
      <span v-if="m.streaming" class="caret" />
      <p v-if="m.error" class="message-error" role="alert">{{ m.error }}</p>
      <div v-if="m.citations.length" class="refs">
        <CitationTag v-for="(c, i) in m.citations" :key="i" :c="c" />
      </div>
      <AudioImportOffer v-if="!m.streaming && m.audioImportOptions?.length" :videos="m.audioImportOptions" />
      <div v-if="m.externalVideos?.length" class="external-results">
        <div class="external-title">B 站候选视频</div>
        <a v-for="video in m.externalVideos" :key="video.bvid" class="external-card" :href="video.url" target="_blank" rel="noopener">
          <img v-if="video.cover" :src="video.cover" alt="" />
          <div>
            <strong>{{ video.title }}</strong>
            <small>{{ video.author || '未知 UP 主' }} · {{ video.duration || '时长未知' }} · {{ fmtPlay(video.play) }}</small>
            <p v-if="video.description">{{ video.description }}</p>
          </div>
        </a>
      </div>
    </template>
    <template v-else>{{ m.text }}</template>

    <!-- 角标悬浮卡片：来源 / 时间范围 / 引用原文 -->
    <div
      v-if="tip && tipCite"
      ref="tipEl"
      class="cite-tip"
      :style="{ left: tip.x + 'px', top: tip.y + 'px' }"
      @mouseenter="holdTip"
      @mouseleave="hideTip"
    >
      <div class="tip-head">
        <span class="tip-idx">引用 {{ tip.i }}{{ tipCite.external ? ' · B 站临时' + (tipCite.source || '字幕') : '' }}</span>
        <span class="tip-time">{{ fmtMin(tipCite.start) }} – {{ fmtMin(tipCite.end) }}</span>
      </div>
      <div class="tip-title">{{ tipCite.title || tipCite.video_id }}</div>
      <div v-if="tipCite.author" class="tip-author">{{ tipCite.author }}</div>
      <p v-if="tipCite.text" class="tip-quote">{{ tipCite.text }}</p>
      <span v-if="refUrl(tipCite)" class="tip-link">点击序号可跳转到 B 站对应位置 ↗</span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.msg {
  max-width: 80%;
  padding: 0.85rem 1.1rem;
  border-radius: 14px;
  font-size: 0.95rem;
  line-height: 1.7;
  word-break: break-word;
}
.msg.q {
  align-self: flex-end;
  background: var(--panel-2);
  color: var(--ink);
  border-bottom-right-radius: 4px;
  white-space: pre-wrap;
}
.msg.a {
  align-self: flex-start;
  max-width: 100%;
  width: 100%;
  padding: .15rem 0;
}
.message-error { margin-top: .45rem; color: #c85a50; font-size: .85rem; }
.who {
  font-size: 0.76rem;
  color: var(--accent-text);
  font-weight: 600;
}
.refs {
  display: flex;
  flex-wrap: wrap;
  margin-top: 0.2rem;
}
.agent-trace {
  margin: .3rem 0 .65rem;
  padding: .25rem 0 .25rem .55rem;
  border-left: 1px solid var(--line);
  font-size: 0.76rem;
}
.trace-title { color: var(--ink-3); cursor: pointer; font-weight: 600; }
.agent-trace[open] .trace-title { margin-bottom: .32rem; }
.trace-step { display: grid; grid-template-columns: 1rem 4.8rem 1fr; gap: 0.25rem; align-items: baseline; color: var(--ink-3); line-height: 1.55; }
.trace-step strong { color: var(--ink-2); font-weight: 600; }
.trace-icon { color: var(--accent); text-align: center; font-weight: 700; }
.trace-step.warning .trace-icon { color: #c58a16; }
.trace-step.failed .trace-icon { color: #ce5b5b; }
.trace-step.running .trace-icon { animation: blink 1s steps(2) infinite; }
.external-results {
  margin-top: 0.8rem;
  border-top: 1px solid var(--line);
  padding-top: 0.7rem;
}
.external-title { font-size: 0.78rem; color: var(--ink-3); margin-bottom: 0.4rem; }
.external-card {
  display: flex; gap: 0.6rem; padding: 0.45rem 0; color: inherit; text-decoration: none;
  border-bottom: 1px solid var(--line);
}
.external-card:hover strong { color: var(--accent-text); }
.external-card img { width: 84px; height: 48px; object-fit: cover; border-radius: 5px; background: var(--panel); }
.external-card strong, .external-card small, .external-card p { display: block; }
.external-card strong { font-size: 0.84rem; line-height: 1.35; }
.external-card small, .external-card p { color: var(--ink-3); font-size: 0.73rem; line-height: 1.35; }
.external-card p { margin: 0.16rem 0 0; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }

/* markdown 排版 */
.markdown :deep(p) {
  margin: 0.55rem 0;
}
.markdown :deep(p:first-child) {
  margin-top: 0;
}
.markdown :deep(p:last-child) {
  margin-bottom: 0;
}
.markdown :deep(strong) {
  font-weight: 700;
  color: var(--ink);
}
.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0.45rem 0;
  padding-left: 1.4rem;
}
.markdown :deep(li) {
  margin: 0.3rem 0;
}
.markdown :deep(li::marker) {
  color: var(--ink-3);
}
.markdown :deep(code) {
  background: var(--panel);
  border: 1px solid var(--line);
  padding: 0.1rem 0.35rem;
  border-radius: 5px;
  font-size: 0.88em;
}
.markdown :deep(a) {
  color: var(--accent);
  text-decoration: none;
}
.markdown :deep(a:hover) {
  text-decoration: underline;
}
/* 句末/段末的引用上标 */
.markdown :deep(.cite) {
  display: inline-block;
  position: relative;
  top: -0.42em;
  margin-left: 2px;
  padding: 0 3px;
  min-width: 14px;
  text-align: center;
  font-size: 0.66rem;
  font-weight: 700;
  line-height: 1.25;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
  background: var(--accent-dim);
  border-radius: 3px;
  text-decoration: none;
  vertical-align: baseline;
}
.markdown :deep(.cite:hover) {
  background: var(--accent-line);
  text-decoration: none;
}
/* 角标悬浮卡片 */
.cite-tip {
  position: fixed;
  z-index: 40;
  width: 272px;
  max-width: calc(100vw - 20px);
  padding: 0.5rem 0.62rem 0.55rem;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 8px 22px rgba(16, 24, 32, 0.08);
  font-size: 0.74rem;
  line-height: 1.5;
  color: var(--ink-2);
  text-align: left;
}
.tip-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}
.tip-idx {
  color: var(--accent);
  font-weight: 700;
}
.tip-time {
  color: var(--ink-3);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
}
.tip-title {
  margin-top: 0.18rem;
  color: var(--ink);
  font-weight: 600;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tip-author {
  color: var(--ink-3);
  font-size: 0.72rem;
}
.tip-quote {
  margin: 0.34rem 0 0;
  padding-left: 0.45rem;
  border-left: 2px solid var(--accent-dim);
  color: var(--ink-3);
  font-size: 0.71rem;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tip-link {
  display: inline-block;
  margin-top: 0.3rem;
  color: var(--accent);
  font-size: 0.71rem;
}
.caret {
  display: inline-block;
  width: 7px;
  height: 1.05em;
  background: var(--accent);
  vertical-align: -2px;
  animation: blink 1s steps(2) infinite;
  margin-left: 2px;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
@media (max-width: 760px) {
  .msg {
    max-width: 94%;
  }
}
</style>
