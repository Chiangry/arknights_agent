import { request } from './client'
import type { AudioImportOption, Video, TaskSnapshot } from '@/types'

export interface CreateTaskResult {
  task_id: string
  kind: 'bili' | 'local'
  title?: string
}

export interface SubtitleCheck {
  cookie: boolean
  has_subtitle: boolean
  subtitle_type: string | null
  /** 视频时长（秒），0 表示未知 */
  duration: number
}

export async function checkSubtitle(url: string): Promise<SubtitleCheck> {
  return request<SubtitleCheck>(`/api/subtitle-check?url=${encodeURIComponent(url)}`)
}

export async function fetchVideos(): Promise<Video[]> {
  const data = await request<{ videos: Video[] }>('/api/videos')
  return data.videos || []
}

export function setTaskPaused(taskId: string, paused: boolean): Promise<TaskSnapshot> {
  return request<TaskSnapshot>(`/api/tasks/${taskId}/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paused }),
  })
}

export async function createBiliImport(url: string): Promise<CreateTaskResult> {
  const fd = new FormData()
  fd.append('kind', 'bili')
  fd.append('url', url)
  return request<CreateTaskResult>('/api/videos', { method: 'POST', body: fd })
}

export async function createLocalImport(file: File): Promise<CreateTaskResult> {
  const fd = new FormData()
  fd.append('kind', 'local')
  fd.append('file', file)
  return request<CreateTaskResult>('/api/videos', { method: 'POST', body: fd })
}

export function importCachedTranscript(video: AudioImportOption): Promise<
  { status: 'exists' } | { status: 'queued'; task_id: string }
> {
  return request('/api/videos/import-transcript', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bvid: video.bvid, title: video.title, author: video.author }),
  })
}

/** 用 EventSource 订阅任务进度，返回关闭函数。 */
export function subscribeTask(
  taskId: string,
  onSnapshot: (snap: TaskSnapshot) => void,
  onSettled: (snap: TaskSnapshot) => void,
  onError?: () => void,
): () => void {
  const es = new EventSource(`${import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'}/api/tasks/${taskId}/stream`)

  const handler = (e: MessageEvent) => {
    const snap: TaskSnapshot = JSON.parse(e.data)
    onSnapshot(snap)
    if (snap.status === 'done' || snap.status === 'error') {
      onSettled(snap)
      es.close()
    }
  }
  es.addEventListener('progress', handler)
  es.addEventListener('done', handler)
  es.onerror = () => {
    es.close()
    onError?.()
  }

  return () => es.close()
}
