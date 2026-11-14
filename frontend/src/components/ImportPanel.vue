<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { ref, watch } from 'vue'
import Input from '@/components/ui/input/Input.vue'
import Tabs from '@/components/ui/tabs/Tabs.vue'
import TabsList from '@/components/ui/tabs/TabsList.vue'
import TabsTrigger from '@/components/ui/tabs/TabsTrigger.vue'
import { TabsContent } from 'reka-ui'
import { checkSubtitle, type SubtitleCheck } from '@/api/videos'

const emit = defineEmits<{
  (e: 'bili', url: string): void
  (e: 'local', file: File): void
}>()

const kind = ref('bili')
const url = ref('')
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

const checking = ref(false)
const probe = ref<SubtitleCheck | null>(null)
const probeError = ref('')

// 换了链接，旧的检测结果作废
watch(url, () => {
  probe.value = null
  probeError.value = ''
})

function mins(sec: number): string {
  return String(Math.round(sec / 60))
}

function pickFile() {
  fileInput.value?.click()
}
function onPicked(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) file.value = f
}
async function detect() {
  const u = url.value.trim()
  if (!u || checking.value) return
  checking.value = true
  probe.value = null
  probeError.value = ''
  try {
    probe.value = await checkSubtitle(u)
  } catch (err: any) {
    probeError.value = err?.message || '检测失败，请检查后端服务'
  } finally {
    checking.value = false
  }
}
const props = defineProps<{ disabled?: boolean }>()

function submit() {
  if (props.disabled) return
  if (kind.value === 'bili') {
    if (!url.value.trim()) return
    emit('bili', url.value.trim())
  } else {
    if (!file.value) return
    emit('local', file.value)
  }
}
</script>

<template>
  <div>
    <Tabs v-model="kind">
      <TabsList aria-label="导入方式" class="mb-4">
        <TabsTrigger value="bili">B 站链接</TabsTrigger>
        <TabsTrigger value="local">本地文件</TabsTrigger>
      </TabsList>

      <TabsContent value="bili">
        <form class="field" @submit.prevent="submit">
          <Input
            v-model="url"
            type="text"
            aria-label="B 站视频链接或 BV 号"
            placeholder="粘贴 B 站链接或 BV 号"
          />
          <Button type="submit" class="btn" :disabled="disabled || !url.trim()">解析入库</Button>
        </form>

        <div class="probe">
          <Button class="link-btn" type="button" variant="link" size="sm" :disabled="!url.trim() || checking" @click="detect">
            {{ checking ? '检测中…' : '检测能否获取字幕' }}
          </Button>

          <div v-if="probeError" class="probe-line err">{{ probeError }}</div>
          <div v-else-if="probe && probe.has_subtitle" class="probe-line ok">
            可直接获取{{ probe.subtitle_type }}，将秒级解析，无需语音转写。
          </div>
          <div v-else-if="probe" class="probe-line warn">
            该视频无可用字幕，时长约 {{ mins(probe.duration) }} 分钟，将走语音转写（按转写时长逐步推进，较慢）。
            <template v-if="!probe.cookie">当前未配置登录 cookie，配置后可能拿到 AI 字幕。</template>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="local">
          <input ref="fileInput" type="file" accept="video/*,audio/*" hidden @change="onPicked" />
          <Button type="button" class="drop" variant="outline" @click="pickFile">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
              <path d="M12 16V4m0 0L7 9m5-5l5 5M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
            </svg>
            <span>
              <b>{{ file ? file.name : '点击选择视频文件' }}</b>
              <span v-if="!file"><br />支持 mp4 / mov / m4a / mp3 等</span>
            </span>
          </Button>
          <Button class="btn wide" type="button" @click="submit" :disabled="disabled || !file">解析入库</Button>
      </TabsContent>
    </Tabs>

    <div class="hint">
      {{ kind === 'bili' ? '优先抓取 B 站 CC 字幕；无字幕时自动转语音识别。' : '本地文件将使用语音识别转写。' }}
    </div>
  </div>
</template>

<style lang="scss" scoped>
.field {
  display: flex;
  align-items: center;
  gap: .6rem;
}
.field input {
  flex: 1;
  min-width: 0;
}
.btn.wide {
  width: 100%;
  margin-top: 1rem;
}
.drop {
  width: 100%;
  height: auto;
  min-height: 96px;
  border: 1px dashed var(--line-strong);
  padding: 1rem;
  text-align: center;
  color: var(--ink-2);
  white-space: normal;
  overflow-wrap: anywhere;
}
.drop:hover {
  border-color: var(--accent-line);
  color: var(--ink);
}
.drop svg {
  width: 24px;
  height: 24px;
  opacity: 0.5;
}
.hint {
  font-size: 0.82rem;
  color: var(--ink-3);
  margin-top: 0.7rem;
}
.probe {
  margin-top: 0.7rem;
}
.link-btn {
  padding: 0;
}
.probe-line {
  margin-top: 0.5rem;
  font-size: 0.85rem;
  line-height: 1.5;
}
.probe-line.ok {
  color: var(--accent-text);
}
.probe-line.warn {
  color: var(--ink-2);
}
.probe-line.err {
  color: #e5484d;
}
@media (max-width: 380px) {
  .field {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
