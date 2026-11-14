import { defineStore } from 'pinia'
import { createBiliImport, createLocalImport, subscribeTask } from '@/api/videos'
import type { TaskSnapshot, ParseStep } from '@/types'

export const STEP_LABELS: Record<ParseStep, string> = {
  fetch: '获取字幕 / 语音转写',
  chunk: '切分文本片段',
  embed: '向量化 embedding',
  index: '写入向量索引',
}
const STEP_ORDER: ParseStep[] = ['fetch', 'chunk', 'embed', 'index']

export const useParseStore = defineStore('parse', {
  state: () => ({
    current: null as TaskSnapshot | null,
    active: false,
    closeFn: null as null | (() => void),
  }),
  getters: {
    /** 四步各自状态：done / current / pending */
    steps(state) {
      const idx = state.current?.step_index ?? -1
      const status = state.current?.status
      return STEP_ORDER.map((key, i) => {
        let st: 'done' | 'current' | 'pending' = 'pending'
        if (status === 'done') st = 'done'
        else if (i < idx) st = 'done'
        else if (i === idx && status === 'processing') st = 'current'
        return { key, label: STEP_LABELS[key], state: st }
      })
    },
  },
  actions: {
    _begin(taskId: string, onSettled?: () => void) {
      this.active = true
      this.current = {
        task_id: taskId, status: 'queued', step: 'fetch', step_index: 0,
        step_label: STEP_LABELS.fetch, pct: 0, message: '排队中',
        video_id: null, source: null, chunk_count: 0, error: null,
        pause_requested: false, paused: false,
      }
      this.closeFn = subscribeTask(
        taskId,
        (snap) => { this.current = snap },
        (snap) => {
          this.current = snap
          this.active = false
          this.closeFn = null
          onSettled?.()
          // 成功后短暂保留完成态，再自动隐藏进度面板；失败则保留错误信息
          if (snap.status === 'done') {
            setTimeout(() => {
              if (this.current?.task_id === taskId && this.current.status === 'done') {
                this.current = null
              }
            }, 1200)
          }
        },
      )
    },
    async startBili(url: string, onSettled?: () => void) {
      const res = await createBiliImport(url)
      this._begin(res.task_id, onSettled)
    },
    async startLocal(file: File, onSettled?: () => void) {
      const res = await createLocalImport(file)
      this._begin(res.task_id, onSettled)
    },
    reset() {
      this.closeFn?.()
      this.current = null
      this.active = false
      this.closeFn = null
    },
  },
})
