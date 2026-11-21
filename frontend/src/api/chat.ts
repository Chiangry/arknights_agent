import { request } from './client'
import type { AgentStep, Citation, GameState, RetrievalScope } from '../types/backend'

export interface StoredMessage {
  id: number
  request_id: string
  role: 'user' | 'assistant'
  content: string
  status: 'running' | 'completed' | 'failed' | 'interrupted'
  created_at: string
  citations: Citation[]
  steps: AgentStep[]
  agent_mode: boolean
  error?: string | null
}

export interface StoredThread {
  id: string
  title: string
  created_at: string
  last_message_at: string | null
  scope: Partial<RetrievalScope>
  scoped_video_title: string | null
  agent_enabled: boolean
  game_state: GameState | null
  running?: boolean
  messages?: StoredMessage[]
}

export type ThreadPatch = Partial<{
  title: string
  scope: RetrievalScope
  scoped_video_title: string | null
  agent_enabled: boolean
}>

const base = '/api/chat/threads'
const json = (method: string, body: object) => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

export const listChatThreads = () => request<StoredThread[]>(base)
export const getChatThread = (id: string) => request<StoredThread>(`${base}/${id}`)
export const createChatThread = (id: string, fields: Omit<ThreadPatch, 'agent_enabled'>) =>
  request<StoredThread>(base, json('POST', { id, ...fields }))
export const patchChatThread = (id: string, changes: ThreadPatch) =>
  request<StoredThread>(`${base}/${id}`, json('PATCH', changes))
export const deleteChatThread = (id: string) => request(`${base}/${id}`, { method: 'DELETE' })
