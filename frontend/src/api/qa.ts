import { API_BASE, ApiError, request } from './client'
import type { AgentStep, AudioImportOption, Citation, ExternalVideo, GameState } from '../types/backend'

export interface AudioConfirmation {
  videos: (Pick<ExternalVideo, 'bvid' | 'title'>
    & { [K in 'author' | 'pubdate' | 'duration' | 'play' | 'description']?: ExternalVideo[K] | null })[]
  max_mib_per_video: number
  timeout_seconds: number
}

export interface ExternalSearchDetails {
  reason?: string
  missing?: string[]
}

export function confirmAudio(taskId: string, selectedBvids: string[]): Promise<{ accepted: boolean }> {
  return request(`/api/ask/${taskId}/audio-confirmation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved: selectedBvids.length > 0, selected_bvids: selectedBvids }),
  })
}

export interface AskHandlers {
  onTask: (taskId: string) => void
  onGameState: (state: GameState) => void
  onPauseState: (paused: boolean) => void
  onAudioConfirmation: (confirmation: AudioConfirmation) => void
  onAudioImportOffer: (videos: AudioImportOption[]) => void
  onCitations: (citations: Citation[]) => void
  onDelta: (text: string) => void
  onAnswerReplace: (text: string, citations: Citation[]) => void
  onExternalSearch: (videos: ExternalVideo[], details: ExternalSearchDetails) => void
  onAgentStep: (step: AgentStep) => void
  onDone: (citations: Citation[]) => void
}

/**
 * POST /api/ask，用 fetch + ReadableStream 解析 SSE（EventSource 不支持 POST）。
 * 事件顺序：citations → 多个 delta → done。
 */
export async function streamAsk(
  question: string,
  handlers: AskHandlers,
  signal: AbortSignal,
  turn: { thread_id: string; request_id: string; web_search: boolean },
): Promise<void> {
  const open = () => fetch(`${API_BASE}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question, ...turn }),
    signal,
  })
  const res = await open().catch(error => {
    // 只重试尚未拿到响应头的网络失败，沿用相同请求 ID。
    if (!(error instanceof TypeError) || signal.aborted) throw error
    return open()
  })
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail || `问答失败 ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let completed = false

  try {
    while (!completed) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分隔事件块
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''

      for (const block of blocks) {
        const lines = block.split('\n')
        let event = 'message'
        let dataStr = ''
        for (const line of lines) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) dataStr += line.slice(5).trim()
        }
        if (!dataStr) continue
        const data = JSON.parse(dataStr)

        if (event === 'task') handlers.onTask(data.task_id)
        else if (event === 'game_state') handlers.onGameState(data)
        else if (event === 'audio_confirmation') handlers.onAudioConfirmation(data)
        else if (event === 'audio_import_offer') handlers.onAudioImportOffer(data.videos)
        else if (event === 'heartbeat') handlers.onPauseState(data.paused === true)
        else if (event === 'citations') handlers.onCitations(data.citations || [])
        else if (event === 'external_search') handlers.onExternalSearch(data.videos || [], {
          reason: data.reason, missing: data.missing,
        })
        else if (event === 'agent_step') handlers.onAgentStep(data)
        else if (event === 'delta') handlers.onDelta(data.text || '')
        else if (event === 'answer_replace') handlers.onAnswerReplace(data.text, data.citations || [])
        else if (event === 'error') throw new Error(data.message || '问答失败')
        else if (event === 'done') {
          handlers.onDone(data.citations || [])
          completed = true
          break
        }
      }
    }
    if (!completed) throw new Error('回答连接已中断，可以重新尝试。')
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
