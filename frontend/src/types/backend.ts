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
  game_id?: 'arknights' | 'endfield' | null
  category_id?: string | null
  stage_name?: string | null
  source_platform?: string | null
  source_url?: string | null
  cover_url?: string | null
  published_at?: string | null
  indexed_at?: string | null
  updated_at?: string | null
  description?: string | null
  summary?: string | null
}

export interface StoredVideoChunk {
  id: string
  chunk_idx: number
  start_sec: number | null
  end_sec: number | null
  source: string | null
  text: string
}

export interface VideoMetadata {
  title?: string
  author?: string | null
  game_id?: 'arknights' | 'endfield' | null
  category_id?: string | null
  stage_name?: string | null
}

export interface VideoMetadataPreview {
  bvid: string
  title: string | null
  author: string | null
  cover_url: string | null
  duration_seconds: number | null
  published_at: string | null
  description: string | null
  suggestion: { game_id: NonNullable<VideoMetadata['game_id']> | null; category_id: string | null }
}
export interface RetrievalScope {
  game_id?: string | null
  category_id?: string | null
  video_ids?: string[]
}

export type ParseStatus = 'queued' | 'processing' | 'done' | 'error'
export type ParseStep = 'fetch' | 'chunk' | 'embed' | 'index'

export interface VisualConfirmation {
  start: number
  seconds: number
  reason: string
  expires_at: number
  segment_count?: number | null
}

export interface VisualWindow {
  start: number
  end: number
  status: 'indexed' | 'empty' | 'failed'
  reason?: string | null
}

export interface VisualCoverage {
  total: number
  processed: number
  with_evidence: number
  empty: number
  failed: VisualWindow[]
}

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
  visual_confirmation?: VisualConfirmation | null
  visual_coverage?: VisualCoverage | null
}

export interface Citation {
  video_id: string | null
  title?: string | null
  author?: string | null
  published_at?: string | null
  stage_name?: string | null
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
  stage: 'video_lookup' | 'knowledge_search' | 'answer_check' | 'bilibili_search' | 'external_subtitles' | 'answer' | 'answer_review'
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
