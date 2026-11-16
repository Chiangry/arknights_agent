// 与后端 FastAPI 接口对齐的类型定义

export interface Video {
  video_id: string
  title: string
  author?: string | null
  source: string
  chunk_count: number
  /** 时长（秒） */
  duration: number
  created_at?: string | null
}

export type ParseStatus = 'queued' | 'processing' | 'done' | 'error'
export type ParseStep = 'fetch' | 'chunk' | 'embed' | 'index'

export interface TaskSnapshot {
  task_id: string
  status: ParseStatus
  step: ParseStep
  step_index: number
  step_label: string
  pct: number
  message: string
  video_id: string | null
  source: string | null
  chunk_count: number
  error: string | null
  pause_requested: boolean
  paused: boolean
}

export interface Citation {
  video_id: string | null
  title?: string | null
  author?: string | null
  start: number
  end: number
  text: string
  external?: boolean
  source?: string | null
}

/** 本地证据不足时，后端仅搜索得到的 B 站候选；尚未下载或入库。 */
export interface ExternalVideo {
  bvid: string
  title: string
  author: string
  description: string
  duration: string
  play: number
  pubdate: number
  cover: string
  url: string
}

/** Agent 对外展示的执行轨迹，不包含模型内部推理。 */
export interface AgentStep {
  stage: 'knowledge_search' | 'answer_check' | 'bilibili_search' | 'external_subtitles' | 'answer' | 'answer_review'
    | 'external_answer' | 'external_review'
    | 'external_audio_1' | 'external_audio_2' | 'external_audio_reuse'
    | 'game_state'
  status: 'running' | 'completed' | 'warning' | 'failed'
  message: string
}

export interface AudioImportOption {
  bvid: string
  title: string
  author: string
  citation_count: number
}

export interface ChatMessage {
  id: number
  role: 'q' | 'a'
  text: string
  citations: Citation[]
  externalVideos?: ExternalVideo[]
  audioImportOptions?: AudioImportOption[]
  agentSteps?: AgentStep[]
  /** 助手消息是否仍在流式输出 */
  streaming?: boolean
  error?: string
}

/** 一次完整对话，用于左侧历史会话列表 */
export interface GameState {
  mode?: string | null
  faction?: string | null
  version?: string | null
  turn?: string | null
  lineup?: string[]
  resources?: Record<string, number>
  options?: { name: string; costs?: Record<string, number>; available?: boolean | null }[]
  goal?: string | null
  last_action?: string | null
}

export interface Conversation {
  id: string
  /** 首条提问截断生成的标题 */
  title: string
  messages: ChatMessage[]
  updatedAt: number
  createdAt?: number
  gameState?: GameState
}
