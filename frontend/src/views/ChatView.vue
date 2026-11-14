<script setup lang="ts">
import { Button } from '@/components/ui/button'
import Checkbox from '@/components/ui/checkbox/Checkbox.vue'
import { computed, nextTick, ref, watch } from 'vue'
import ChatMessage from '@/components/ChatMessage.vue'
import Composer from '@/components/Composer.vue'
import ScrollArea from '@/components/ScrollArea.vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
const request = computed(() => chat.activeRequest)
const gameState = computed(() => chat.gameState)
function toggleCandidate(bvid: string, checked: boolean | 'indeterminate') {
  if (!request.value) return
  const selected = request.value.selectedBvids.filter((id) => id !== bvid)
  request.value.selectedBvids = checked === true ? [...selected, bvid] : selected
}
const audioRunning = computed(() => chat.messages.at(-1)?.agentSteps?.some(
  (step) => step.stage.startsWith('external_audio_') && step.status === 'running',
))
const publishDateFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: 'long', day: 'numeric',
})
const playFormatter = new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 })

function publishDate(seconds?: number | null): string {
  const date = new Date((seconds ?? 0) * 1000)
  return seconds && seconds > 0 && Number.isFinite(date.getTime())
    ? `${publishDateFormatter.format(date)}发布` : '发布时间未知'
}

const box = ref<InstanceType<typeof ScrollArea> | null>(null)
/** 用户上翻看历史时不再强行跟随到底部 */
const stick = ref(true)

function onScroll() {
  const el = box.value?.getViewport()
  if (!el) return
  stick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 48
}

function scrollToBottom() {
  const el = box.value?.getViewport()
  if (el) el.scrollTop = el.scrollHeight
}

async function follow() {
  await nextTick()
  if (stick.value) scrollToBottom()
}

watch(() => chat.messages.length, follow)
// 流式追加时也滚动
watch(() => {
  const message = chat.messages.at(-1)
  return [message?.text.length, message?.agentSteps?.map((step) => step.message).join(), request.value?.audioConfirmation]
}, follow)
watch(() => chat.messages.at(-1)?.streaming, follow)
// 切换会话后回到最新位置
watch(() => chat.activeId, () => {
  stick.value = true
  void follow()
})

function onSend(q: string) {
  stick.value = true
  chat.ask(q)
}
</script>

<template>
  <section class="chat-view">
    <div class="chat-main" :class="{ 'is-empty': !chat.messages.length }">
      <ScrollArea ref="box" class="chat" label="问答消息" @scroll="onScroll">
        <div class="thread">
          <div v-if="!chat.messages.length" class="empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 12a8 8 0 01-8 8H5l-2 2V12a8 8 0 018-8h2a8 8 0 018 8z" />
            </svg>
            <h1>想了解视频里的什么内容？</h1>
            <small>提问后会优先从你的知识库寻找答案。</small>
          </div>
          <ChatMessage v-for="m in chat.messages" :key="m.id" :m="m" />
          <Button v-if="chat.messages.at(-1)?.error && !request" class="retry" variant="link" @click="chat.retryLast()">重新回答</Button>

          <div v-if="request?.audioConfirmation" class="audio-confirmation" aria-label="确认下载和转写">
            <strong>字幕不足，是否下载音频并转写？</strong>
            <p>每个音轨上限 {{ request.audioConfirmation.max_mib_per_video }} MiB，转写后会清理。</p>
            <ul>
              <li v-for="video in request.audioConfirmation.videos" :key="video.bvid" class="candidate">
                <div class="candidate-option">
                  <Checkbox :id="`transcribe-${request.taskId}-${video.bvid}`"
                    :model-value="request.selectedBvids.includes(video.bvid)" :disabled="request.confirmationBusy"
                    @update:model-value="checked => toggleCandidate(video.bvid, checked)" />
                  <label :for="`transcribe-${request.taskId}-${video.bvid}`">{{ video.title }}</label>
                </div>
                <div class="candidate-meta">
                  <span>UP 主：{{ video.author || '未知' }}</span>
                  <span>{{ publishDate(video.pubdate) }}</span>
                  <span v-if="video.duration">时长 {{ video.duration }}</span>
                  <span v-if="video.play != null">{{ playFormatter.format(video.play) }}播放</span>
                  <a :href="`https://www.bilibili.com/video/${encodeURIComponent(video.bvid)}/`" target="_blank" rel="noopener noreferrer">打开原视频</a>
                </div>
                <p v-if="video.description && video.description !== '-'" class="candidate-description">{{ video.description }}</p>
              </li>
            </ul>
            <div class="confirmation-actions">
              <Button variant="default" size="sm" type="button" :disabled="request.confirmationBusy || !request.selectedBvids.length" @click="chat.decideAudio(request.selectedBvids)">
                转写所选（{{ request.selectedBvids.length }}）
              </Button>
              <Button variant="outline" size="sm" type="button" :disabled="request.confirmationBusy" @click="chat.decideAudio(request.audioConfirmation.videos.map(video => video.bvid))">
                全部转写
              </Button>
              <Button variant="ghost" size="sm" type="button" :disabled="request.confirmationBusy" @click="chat.decideAudio([])">跳过</Button>
              <span>等待 {{ request.audioConfirmation.timeout_seconds }} 秒后自动跳过</span>
            </div>
            <p v-if="request.confirmationError" role="alert">{{ request.confirmationError }}</p>
          </div>
        </div>
      </ScrollArea>
      <div class="composer-dock">
        <div class="strategy-controls">
          <Button size="sm" :variant="chat.strategyEnabled ? 'secondary' : 'ghost'"
            type="button" :disabled="!!request" :aria-pressed="chat.strategyEnabled" @click="chat.toggleStrategy()">
            对局助手
          </Button>
          <Button v-if="chat.strategyEnabled && chat.activeId" size="sm" variant="ghost"
            type="button" :disabled="!!request" @click="onSend('换一局')">换一局</Button>
        </div>
        <details v-if="chat.strategyEnabled && gameState" class="game-state">
          <summary>当前对局<span v-if="gameState.turn"> · {{ gameState.turn }}</span></summary>
          <div>
            <p v-if="gameState.mode || gameState.faction || gameState.version">{{ [gameState.mode, gameState.faction, gameState.version].filter(Boolean).join(' · ') }}</p>
            <p v-if="gameState.lineup?.length">阵容 {{ gameState.lineup.join('、') }}</p>
            <p v-if="Object.keys(gameState.resources ?? {}).length">资源 {{ Object.entries(gameState.resources ?? {}).map(([name, value]) => name + ' ' + value).join('、') }}</p>
            <p v-if="gameState.options?.length">可选 {{ gameState.options.map(option => option.name).join('、') }}</p>
            <p v-if="gameState.goal">目标 {{ gameState.goal }}</p>
            <p v-if="gameState.last_action">已执行 {{ gameState.last_action }}</p>
          </div>
        </details>
        <div v-if="request?.taskId && (audioRunning || request.pauseRequested)" class="audio-controls">
          <Button variant="outline" size="sm" type="button" :disabled="request.pauseBusy" @click="chat.togglePause()">
            {{ request.pauseRequested ? '继续音频处理' : '暂停音频处理' }}
          </Button>
          <span v-if="request.pauseError" role="alert">{{ request.pauseError }}</span>
          <span v-else-if="request.pauseRequested">{{ request.paused ? '已暂停' : '等待音频处理到暂停点…' }}</span>
        </div>
        <Composer v-model="chat.drafts[chat.activeId]" :disabled="!!request"
          :placeholder="chat.strategyEnabled ? '描述当前回合、资源和可选动作…' : '输入你的问题…'" @send="onSend" />
        <p class="composer-hint">Enter 发送 <span aria-hidden="true">·</span> Shift + Enter 换行</p>
      </div>
    </div>
  </section>
</template>

<style lang="scss" scoped>
.audio-confirmation {
  margin: .75rem 0;
  padding: .8rem 1rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  font-size: .9rem;
}
.audio-confirmation p, .audio-confirmation ul { margin: .35rem 0; }
.audio-confirmation ul { list-style: none; padding-left: 0; }
.candidate + .candidate { margin-top: .5rem; }
.candidate-option { display: flex; align-items: center; gap: .45rem; font-weight: 600; }
.candidate-meta, .audio-confirmation .candidate-description { margin-left: 1.4rem; color: var(--ink-3); font-size: .8rem; }
.candidate-meta { display: flex; flex-wrap: wrap; gap: .15rem .7rem; }
.candidate-meta a { color: var(--accent-text); }
.candidate-description { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.confirmation-actions { display: flex; align-items: center; flex-wrap: wrap; gap: .6rem; }
.confirmation-actions span { color: var(--ink-3); font-size: .8rem; }

.chat-view {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 0;
}
.chat-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
}
.chat {
  min-height: 0;
}
.thread, .composer-dock {
  width: 100%;
  max-width: 820px;
  margin-inline: auto;
  padding-inline: clamp(1rem, 4vw, 2.5rem);
}
.thread { min-height: 100%; display: flex; flex-direction: column; gap: 1.5rem; padding-block: 1.9rem .65rem; }
.composer-dock { flex: none; padding-block: .5rem 1rem; }
.strategy-controls { display: flex; align-items: center; gap: .3rem; margin-bottom: .35rem; }
.game-state { margin-bottom: .5rem; font-size: .8rem; color: var(--ink-2); }
.game-state summary { width: fit-content; cursor: pointer; }
.game-state > div { max-height: 8rem; overflow-y: auto; overflow-wrap: anywhere; padding: .25rem .55rem; }
.composer-hint { margin-top: .3rem; text-align: right; font-size: .7rem; color: var(--ink-3); }
.is-empty { display: flex; flex-direction: column; justify-content: center; }
.is-empty .chat { flex: 0 1 auto; }
.is-empty .thread { min-height: auto; padding-block: .8rem 1rem; }
.audio-controls { display: flex; flex-wrap: wrap; gap: .55rem; padding-bottom: .45rem; font-size: .82rem; color: var(--ink-3); }
.audio-controls button, .retry { color: var(--accent-text); }
.retry { align-self: flex-start; font-size: .85rem; }
.empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--ink-3);
}
.empty svg {
  width: 27px;
  height: 27px;
  color: var(--accent);
  margin-bottom: .85rem;
}
.empty h1 { color: var(--ink); font-weight: 650; font-size: clamp(1.2rem, 3vw, 1.65rem); letter-spacing: -.025em; margin-bottom: .3rem; }
@media (max-width: 860px) {
  .chat-view {
    flex-direction: column;
  }
  .composer-hint { display: none; }
}
</style>
