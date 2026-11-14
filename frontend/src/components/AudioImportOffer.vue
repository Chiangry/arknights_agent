<script setup lang="ts">
import { Button } from '@/components/ui/button'
import Checkbox from '@/components/ui/checkbox/Checkbox.vue'
import { computed, onUnmounted, reactive, ref, useId } from 'vue'
import { importCachedTranscript, subscribeTask } from '@/api/videos'
import type { AudioImportOption } from '@/types'

const props = defineProps<{ videos: AudioImportOption[] }>()
const offerId = useId()
const mostCited = computed(() => Math.max(0, ...props.videos.map((video) => video.citation_count)))
const selected = ref(props.videos.filter(recommended).map((video) => video.bvid))
const states = reactive<Record<string, { status: 'running' | 'done' | 'error'; message: string }>>({})
const subscriptions = new Map<string, () => void>()
const dismissed = ref(false)
let unmounted = false

function recommended(video: AudioImportOption) {
  return mostCited.value > 0 && video.citation_count === mostCited.value
}

function toggleSelection(bvid: string, checked: boolean | 'indeterminate') {
  const remaining = selected.value.filter((id) => id !== bvid)
  selected.value = checked === true ? [...remaining, bvid] : remaining
}

const available = computed(() => props.videos.filter((video) =>
  !states[video.bvid] || states[video.bvid].status === 'error',
))

async function save(video: AudioImportOption) {
  const id = video.bvid
  states[id] = { status: 'running', message: '正在提交…' }
  try {
    const result = await importCachedTranscript(video)
    if (unmounted) return
    if (result.status === 'exists') {
      states[id] = { status: 'done', message: '已在知识库' }
      return
    }
    subscriptions.set(id, subscribeTask(
      result.task_id,
      (snap) => { states[id] = { status: 'running', message: snap.message } },
      (snap) => {
        subscriptions.delete(id)
        states[id] = snap.status === 'done'
          ? { status: 'done', message: '已入库' }
          : { status: 'error', message: snap.error || '入库失败，可重试' }
      },
      () => {
        subscriptions.delete(id)
        states[id] = { status: 'error', message: '进度连接断开，可重试检查' }
      },
    ))
  } catch (error) {
    states[id] = { status: 'error', message: error instanceof Error ? error.message : '入库失败' }
  }
}

function saveSelected(all = false) {
  for (const video of available.value) {
    if (all || selected.value.includes(video.bvid)) void save(video)
  }
}

onUnmounted(() => {
  unmounted = true
  for (const unsubscribe of subscriptions.values()) unsubscribe()
})
</script>

<template>
  <section v-if="!dismissed" class="import-offer" aria-label="转写视频入库">
    <strong>要将已转写的视频加入知识库吗？</strong>
    <p>按本轮回答实际引用的不同片段计数，引用最多的视频会优先推荐。</p>
    <ul>
      <li v-for="video in videos" :key="video.bvid">
        <div class="option">
          <Checkbox
            :id="`${offerId}-${video.bvid}`"
            :model-value="selected.includes(video.bvid)"
            :disabled="states[video.bvid]?.status === 'running' || states[video.bvid]?.status === 'done'"
            @update:model-value="checked => toggleSelection(video.bvid, checked)"
          />
          <label :for="`${offerId}-${video.bvid}`">{{ video.title }}</label>
        </div>
        <small>引用 {{ video.citation_count }} 段<span v-if="recommended(video)"> · 推荐入库</span></small>
        <small v-if="states[video.bvid]" role="status">{{ states[video.bvid].message }}</small>
      </li>
    </ul>
    <div class="actions">
      <Button size="sm" type="button" :disabled="!available.some(video => selected.includes(video.bvid))" @click="saveSelected()">
        入库所选
      </Button>
      <Button variant="outline" size="sm" type="button" :disabled="!available.length" @click="saveSelected(true)">全部入库</Button>
      <Button variant="ghost" size="sm" type="button" @click="dismissed = true">暂不入库</Button>
    </div>
  </section>
</template>

<style scoped>
.import-offer { margin-top: .75rem; padding: .7rem; border: 1px solid var(--line); border-radius: 8px; font-size: .85rem; }
p, ul { margin: .3rem 0; }
ul { padding: 0; list-style: none; }
li + li { margin-top: .35rem; }
.option { display: flex; align-items: center; gap: .4rem; }
small { display: block; padding-left: 1.3rem; color: var(--ink-3); }
.actions { display: flex; flex-wrap: wrap; gap: .45rem; }
</style>
