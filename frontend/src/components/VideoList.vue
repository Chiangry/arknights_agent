<script setup lang="ts">
import { Button } from '@/components/ui/button'
import Input from '@/components/ui/input/Input.vue'
import NativeSelect from '@/components/ui/native-select/NativeSelect.vue'
import Card from '@/components/ui/card/Card.vue'
import { computed, ref } from 'vue'
import { useVideosStore } from '@/stores/videos'
import type { Video } from '@/types'

const videos = useVideosStore()
defineEmits<{ add: [] }>()
const query = ref('')
const source = ref<'all' | 'bili' | 'local'>('all')
const dateFormatter = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' })

function isBili(video: Video): boolean {
  return /^BV[0-9A-Za-z]{10}$/.test(video.video_id)
}

const filtered = computed(() => {
  const terms = query.value.toLowerCase().trim().split(/\s+/).filter(Boolean)
  return videos.list.filter((video) => {
    if (source.value !== 'all' && isBili(video) !== (source.value === 'bili')) return false
    const searchable = [video.title, video.author, video.video_id, video.source].join(' ').toLowerCase()
    return terms.every((term) => searchable.includes(term))
  })
})

function duration(seconds: number): string {
  if (seconds <= 0 || !Number.isFinite(seconds)) return '时长未知'
  const total = Math.round(seconds)
  const minutes = Math.floor(total / 60)
  return `${minutes}:${String(total % 60).padStart(2, '0')}`
}

function importedAt(video: Video): string {
  if (!video.created_at) return ''
  const date = new Date(video.created_at)
  return Number.isFinite(date.getTime()) ? dateFormatter.format(date) : ''
}

function reset() {
  query.value = ''
  source.value = 'all'
}
</script>

<template>
  <section class="library-list" aria-label="已导入视频">
    <header class="library-toolbar">
      <div class="filters">
        <label class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="5.5" /><path d="m15 15 4 4" /></svg>
          <Input v-model="query" type="search" aria-label="搜索已导入视频" placeholder="搜索标题、UP 主或 BV 号" />
        </label>
        <NativeSelect v-model="source" aria-label="按视频来源筛选">
          <option value="all">全部来源</option>
          <option value="bili">B 站</option>
          <option value="local">本地</option>
        </NativeSelect>
      </div>
      <slot name="actions" />
    </header>

    <div v-if="videos.error" class="list-state" role="alert">
      {{ videos.error }} <Button variant="link" size="sm" type="button" @click="videos.load()">重试</Button>
    </div>
    <div v-else-if="videos.loading && !videos.list.length" class="list-state" role="status">正在加载视频库…</div>
    <div v-else-if="!videos.list.length" class="list-state empty">
      <strong>视频库还是空的</strong>
      <p>添加 B 站或本地视频后，就可以在问答页提问。</p>
      <Button variant="link" size="sm" type="button" @click="$emit('add')">添加第一个视频 ↗</Button>
    </div>
    <template v-else>
      <div v-if="!filtered.length" class="list-state">
        没有符合条件的视频。<Button variant="link" size="sm" type="button" @click="reset">清除筛选</Button>
      </div>
      <ul v-else class="cards">
        <li v-for="video in filtered" :key="video.video_id">
          <Card class="video-card">
            <div class="card-top">
              <span class="asset-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3.5" y="5.5" width="17" height="13" rx="2" /><path d="m10 9 5 3-5 3z" /></svg>
              </span>
              <span class="source">{{ isBili(video) ? 'B 站' : '本地' }} · {{ duration(video.duration) }}</span>
            </div>
            <h3 :title="video.title || video.video_id">{{ video.title || video.video_id }}</h3>
            <p class="author">{{ video.author || (isBili(video) ? video.video_id : '本地文件') }}</p>
            <div class="card-meta">
              <span>{{ video.chunk_count }} 个片段</span>
              <span v-if="video.source">{{ video.source }}</span>
              <span v-if="importedAt(video)">入库于 {{ importedAt(video) }}</span>
            </div>
            <a v-if="isBili(video)" :href="`https://www.bilibili.com/video/${video.video_id}/`" target="_blank" rel="noopener noreferrer" :aria-label="`打开原视频：${video.title || video.video_id}`">打开原视频 ↗</a>
          </Card>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.library-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .65rem; margin-bottom: 1rem; }
.author, .card-meta, .card-top { font-size: .8rem; color: var(--ink-3); }
.filters { flex: 1; min-width: min(100%, 300px); display: flex; gap: .5rem; }
.filters :deep(input), .filters :deep(select) {
  min-height: 40px;
  padding: .4rem .65rem;
  background: var(--panel);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}
.search { position: relative; flex: 1; min-width: 0; max-width: 330px; }
.search svg { position: absolute; top: 11px; left: 9px; width: 18px; height: 18px; color: var(--ink-3); pointer-events: none; }
.filters :deep(input) { width: 100%; padding-left: 2rem; }
.filters :deep(select) { padding-right: 2.1rem; }
.cards { list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 250px), 1fr)); gap: .8rem; }
.video-card { display: flex; flex-direction: column; gap: .4rem; height: 100%; min-width: 0; padding: 1rem; border: 1px solid var(--line); border-radius: var(--radius); box-shadow: none; transition: border-color .15s; }
.video-card:hover, .video-card:focus-within { border-color: var(--accent-line); }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: .5rem; margin-bottom: .25rem; }
.asset-icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 9px; background: var(--accent-dim); color: var(--accent); }
.asset-icon svg { width: 18px; height: 18px; }
.source { font-variant-numeric: tabular-nums; }
h3 { font-size: .96rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.author { overflow-wrap: anywhere; }
.card-meta { display: flex; gap: .25rem .55rem; flex-wrap: wrap; margin-top: auto; padding-top: .55rem; }
.video-card a, .list-state button { color: var(--accent-text); font-size: .82rem; align-self: flex-start; }
.video-card a:hover, .list-state button:hover { text-decoration: underline; }
.list-state { padding: 1.1rem 0; color: var(--ink-3); font-size: .9rem; }
.empty { padding: 3rem 1rem; border: 1px dashed var(--line-strong); border-radius: var(--radius); text-align: center; }
.empty strong { color: var(--ink); }
.empty p { margin: .3rem 0 .65rem; }
@media (max-width: 560px) {
  .search { max-width: none; }
}
</style>
