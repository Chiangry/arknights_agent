<script setup lang="ts">
import { Button } from '@/components/ui/button'
import Sheet from '@/components/ui/sheet/Sheet.vue'
import SheetContent from '@/components/ui/sheet/SheetContent.vue'
import SheetTitle from '@/components/ui/sheet/SheetTitle.vue'
import SheetDescription from '@/components/ui/sheet/SheetDescription.vue'
import { DialogTrigger } from 'reka-ui'
import { onMounted, ref } from 'vue'
import ImportPanel from '@/components/ImportPanel.vue'
import ParseProgress from '@/components/ParseProgress.vue'
import VideoList from '@/components/VideoList.vue'
import { useVideosStore } from '@/stores/videos'
import { useParseStore } from '@/stores/parse'
import { ApiError } from '@/api/client'

const videos = useVideosStore()
const parse = useParseStore()
const notice = ref('')
const submitting = ref(false)
const drawerOpen = ref(false)

onMounted(() => videos.load())

function openImport() {
  drawerOpen.value = true
}

function refresh() {
  videos.load()
}

async function onBili(url: string) {
  if (parse.active || submitting.value) return
  submitting.value = true
  notice.value = ''
  try {
    await parse.startBili(url, refresh)
  } catch (e: any) {
    notice.value = e instanceof ApiError ? e.message : '创建任务失败'
  } finally {
    submitting.value = false
  }
}

async function onLocal(file: File) {
  if (parse.active || submitting.value) return
  submitting.value = true
  notice.value = ''
  try {
    await parse.startLocal(file, refresh)
  } catch (e: any) {
    notice.value = e instanceof ApiError ? e.message : '上传失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="library">
    <Sheet v-model:open="drawerOpen">
      <div class="page-head">
        <h1>视频库</h1>
        <p>{{ videos.list.length }} 个视频 <span aria-hidden="true">·</span> {{ videos.totalChunks }} 个可检索片段</p>
      </div>

      <Button v-if="parse.current && !drawerOpen" type="button" class="import-status" variant="outline" @click="openImport">
        <span>{{ parse.current.message }}</span><span>查看进度 ↗</span>
      </Button>

      <VideoList @add="openImport">
        <template #actions>
          <DialogTrigger as-child>
            <Button type="button" class="primary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              添加视频
            </Button>
          </DialogTrigger>
        </template>
      </VideoList>

      <SheetContent class="quiet-scroll gap-0 overflow-y-auto bg-card">
        <header class="drawer-head">
          <div>
            <SheetTitle>添加视频</SheetTitle>
            <SheetDescription>导入 B 站链接或本地文件。</SheetDescription>
          </div>
        </header>
        <div class="drawer-body">
          <ImportPanel :disabled="parse.active || submitting" @bili="onBili" @local="onLocal" />
          <p v-if="notice" class="notice" role="alert">{{ notice }}</p>
          <ParseProgress />
        </div>
      </SheetContent>
    </Sheet>
  </section>
</template>

<style lang="scss" scoped>
.library { padding-block: .3rem 1.5rem; }
.page-head { margin-bottom: 1.5rem; }
.page-head h1 {
  font-size: clamp(1.55rem, 3vw, 2rem);
  font-weight: 700;
  letter-spacing: -.035em;
}
.page-head p {
  color: var(--ink-3);
  font-size: 0.9rem;
  margin-top: 0.25rem;
}
.notice {
  margin-top: 0.8rem;
  font-size: 0.85rem;
  color: #d4483b;
}
.primary { min-height: 40px; font-weight: 650; }
.import-status { display: flex; gap: 1rem; width: 100%; justify-content: space-between; padding: .65rem .8rem; margin-bottom: .9rem; border: 1px solid var(--line); border-radius: var(--radius-sm); text-align: left; color: var(--ink-2); font-size: .82rem; }
.import-status span:last-child { flex: none; color: var(--accent-text); }
.drawer-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1.25rem 3rem 1.25rem 1.4rem; border-bottom: 1px solid var(--line); }
.drawer-head h2 { font-size: 1.1rem; }
.drawer-head p { color: var(--ink-3); font-size: .86rem; margin-top: .2rem; }
.drawer-body { padding: 1.25rem 1.4rem; }
</style>
