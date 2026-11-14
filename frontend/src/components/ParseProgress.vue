<script setup lang="ts">
import { Button } from '@/components/ui/button'
import Progress from '@/components/ui/progress/Progress.vue'
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useParseStore } from '@/stores/parse'
import { setTaskPaused } from '@/api/videos'

const parse = useParseStore()
const { current, steps } = storeToRefs(parse)
const busy = ref(false)
const pauseError = ref('')

async function togglePause() {
  const task = current.value
  if (!task || busy.value) return
  busy.value = true
  pauseError.value = ''
  try {
    const snapshot = await setTaskPaused(task.task_id, !task.pause_requested)
    if (current.value?.task_id === task.task_id && parse.active) {
      current.value.pause_requested = snapshot.pause_requested
      current.value.paused = snapshot.paused
    }
  } catch (error) {
    pauseError.value = error instanceof Error ? error.message : '操作失败'
  } finally {
    busy.value = false
  }
}

// 字幕/文本来源 → 文案与强调色（#17d1ff 仅作点缀）
const srcLine = computed(() => {
  const s = current.value?.source
  if (!s) return null
  const map: Record<string, { label: string; cls: string }> = {
    'CC字幕': { label: 'UP主CC字幕（最准）', cls: 'cc' },
    'AI字幕': { label: 'B站AI字幕（自动生成）', cls: 'ai' },
    '音频转写': { label: '语音识别转写（whisper）', cls: 'asr' },
  }
  return map[s] ?? { label: s, cls: '' }
})
</script>

<template>
  <div v-if="current" class="panel progress">
    <div class="head">
      <span class="name">{{ current.video_id || current.message }}</span>
      <span class="pct">{{ current.pct }}%</span>
      <Button v-if="parse.active" variant="outline" size="sm" type="button" :disabled="busy" @click="togglePause">
        {{ current.pause_requested ? '继续' : '暂停' }}
      </Button>
    </div>
    <Progress :model-value="current.pct" aria-label="入库进度" class="h-1.5" />

    <div class="steps">
      <div
        v-for="(s, i) in steps"
        :key="s.key"
        class="step"
        :class="s.state"
      >
        <span class="dot">
          <svg v-if="s.state === 'done'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
            <path d="M5 13l4 4L19 7" />
          </svg>
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span class="t">{{ s.label }}</span>
      </div>
    </div>

    <p v-if="current.status === 'error'" class="err">解析失败：{{ current.error }}</p>
    <template v-else>
      <p v-if="srcLine" class="src" :class="srcLine.cls">文本来源：{{ srcLine.label }}</p>
      <p class="msg">{{ current.paused ? '已暂停' : current.pause_requested ? '正在暂停…' : current.message }}</p>
    </template>
    <p v-if="pauseError" class="err">{{ pauseError }}</p>
  </div>
</template>

<style lang="scss" scoped>
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 1.4rem;
  box-shadow: var(--shadow);
}
.progress {
  margin-top: 1.1rem;
}
.head {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin-bottom: 0.8rem;
}
.name {
  font-weight: 600;
  font-size: 0.92rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pct {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  color: var(--accent);
}
.steps {
  margin-top: 1rem;
  display: grid;
  gap: 0.7rem;
}
.step {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  font-size: 0.9rem;
}
.dot {
  width: 22px;
  height: 22px;
  flex: none;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 0.72rem;
  font-weight: 700;
  background: var(--panel-2);
  color: var(--ink-3);
  border: 1px solid var(--line);
}
.dot svg {
  width: 12px;
  height: 12px;
}
.step.current .dot {
  color: var(--accent);
  border-color: var(--accent-line);
}
.step.done .dot {
  background: transparent;
  color: var(--accent);
  border-color: var(--accent);
}
.t {
  color: var(--ink-2);
}
.step.done .t {
  color: var(--ink);
}
.msg {
  margin-top: 0.9rem;
  font-size: 0.82rem;
  color: var(--ink-3);
}
.src {
  margin-top: 0.9rem;
  font-size: 0.86rem;
  font-weight: 600;
}
.src.cc {
  color: #1e9e5a;
}
.src.ai {
  color: var(--accent);
}
.src.asr {
  color: var(--ink-2);
}
.err {
  margin-top: 0.9rem;
  font-size: 0.85rem;
  color: #d4483b;
}
</style>
