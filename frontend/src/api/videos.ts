import { API_BASE, request } from './client'
import type { AudioImportOption, Video, TaskSnapshot, VideoMetadata, VideoMetadataPreview, StoredVideoChunk, VisualWindow } from '../types/backend'

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

export function fetchVideoChunks(videoId: string, query: string, limit: number, offset: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ query, limit: String(limit), offset: String(offset) })
  return request<{ total: number; chunks: StoredVideoChunk[] }>(
    `/api/videos/${encodeURIComponent(videoId)}/chunks?${params}`, { signal },
  )
}

export async function searchBilibili(query: string) {
  const data = await request<{ videos: import('../types/backend').ExternalVideo[] }>(
    `/api/search/bilibili?query=${encodeURIComponent(query)}`,
  )
  return data.videos
}

export function setTaskPaused(taskId: string, paused: boolean): Promise<TaskSnapshot> {
  return request<TaskSnapshot>(`/api/tasks/${taskId}/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paused }),
  })
}

export async function createBiliImport(url: string, metadata: VideoMetadata = {}): Promise<CreateTaskResult> {
  const fd = new FormData()
  fd.append('kind', 'bili')
  fd.append('url', url)
  fd.append('metadata', JSON.stringify(metadata))
  return request<CreateTaskResult>('/api/videos', { method: 'POST', body: fd })
}

export async function decideVisualUpload(taskId: string, approved: boolean): Promise<void> {
  await request(`/api/tasks/${encodeURIComponent(taskId)}/visual-confirmation`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved }),
  })
}

export async function fetchVisualCoverage(videoId: string, signal?: AbortSignal) {
  return request<{ duration: number | null; windows: VisualWindow[] }>(
    `/api/videos/${encodeURIComponent(videoId)}/visual-coverage`, { signal },
  )
}

export async function createLocalImport(file: File, metadata: VideoMetadata = {}): Promise<CreateTaskResult> {
  const fd = new FormData()
  fd.append('kind', 'local')
  fd.append('file', file)
  fd.append('metadata', JSON.stringify(metadata))
  return request<CreateTaskResult>('/api/videos', { method: 'POST', body: fd })
}

export function updateVideo(videoId: string, metadata: VideoMetadata): Promise<Video> {
  return request(`/api/videos/${encodeURIComponent(videoId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(metadata),
  })
}

export async function deleteVideo(videoId: string): Promise<void> {
  await request(`/api/videos/${encodeURIComponent(videoId)}`, { method: 'DELETE' })
}

export function previewVideoMetadata(url: string): Promise<VideoMetadataPreview> {
  return request(`/api/video-metadata?url=${encodeURIComponent(url)}`)
}

export function refreshVideoMetadata(videoId: string): Promise<Video> {
  return request(`/api/videos/${encodeURIComponent(videoId)}/refresh-metadata`, { method: 'POST' })
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
  const es = new EventSource(`${API_BASE}/api/tasks/${taskId}/stream`)

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
