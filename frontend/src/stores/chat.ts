import { defineStore } from 'pinia'
import { confirmAudio, streamAsk } from '@/api/qa'
import type { AudioConfirmation } from '@/api/qa'
import { setTaskPaused } from '@/api/videos'
import type { ChatMessage, Conversation, GameState } from '@/types'

let seq = 0
const MAX_HISTORY = 5
const STORAGE_KEY = 'video-rag-conversations'
const LEGACY_KEY = 'video-rag-chat'
const MAX_CONVERSATIONS = 50

function newId(): string {
  return `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function titleOf(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === 'q' && m.text.trim())
  const title = (first?.text || '').replace(/\s+/g, ' ').trim()
  return title.length > 20 ? `${title.slice(0, 20)}…` : title || '新对话'
}

function newRequest() {
  return {
    taskId: '',
    pauseRequested: false,
    paused: false,
    pauseBusy: false,
    pauseError: '',
    audioConfirmation: null as AudioConfirmation | null,
    selectedBvids: [] as string[],
    confirmationBusy: false,
    confirmationError: '',
  }
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversations: [] as Conversation[],
    activeId: '',
    restored: false,
    requests: {} as Record<string, ReturnType<typeof newRequest>>,
    drafts: {} as Record<string, string>,
    newChatStrategy: false,
  }),
  getters: {
    messages(state): ChatMessage[] {
      return state.conversations.find((c) => c.id === state.activeId)?.messages ?? []
    },
    orderedConversations(state): Conversation[] {
      return [...state.conversations].sort((a, b) =>
        (b.createdAt ?? b.updatedAt) - (a.createdAt ?? a.updatedAt) || b.id.localeCompare(a.id),
      )
    },
    activeRequest: (state) => state.requests[state.activeId],
    gameState: (state): GameState | undefined => state.conversations.find((c) => c.id === state.activeId)?.gameState,
    strategyEnabled(): boolean {
      return this.activeId ? this.gameState !== undefined : this.newChatStrategy
    },
    runningIds: (state) => Object.keys(state.requests),
  },
  actions: {
    restore() {
      if (this.restored) return
      this.restored = true
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (raw) {
          const data = JSON.parse(raw)
          if (Array.isArray(data?.conversations)) {
            this.conversations = data.conversations.map((c: Conversation) => ({
              ...c,
              createdAt: c.createdAt ?? c.updatedAt,
              messages: c.messages.map((m) => m.streaming
                ? { ...m, streaming: false, error: '页面已重新加载，本轮回答未完成。' }
                : m),
            }))
            this.activeId = this.conversations.some((c) => c.id === data.activeId) ? data.activeId : ''
            seq = Math.max(0, ...this.conversations.flatMap((c) => c.messages.map((m) => m.id)))
            return
          }
        }
      } catch {
        /* 忽略损坏的缓存 */
      }
      try {
        const arr = JSON.parse(localStorage.getItem(LEGACY_KEY) || 'null')
        if (Array.isArray(arr) && arr.length) {
          const id = newId()
          const now = Date.now()
          const messages = arr.map((m: ChatMessage) => ({ ...m, streaming: false }))
          this.conversations = [{ id, title: titleOf(messages), messages, updatedAt: now, createdAt: now }]
          this.activeId = id
          seq = Math.max(0, ...messages.map((m: ChatMessage) => m.id))
          this.persist()
          localStorage.removeItem(LEGACY_KEY)
        }
      } catch {
        /* 忽略损坏的缓存 */
      }
    },
    persist() {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          conversations: this.conversations, activeId: this.activeId,
        }))
      } catch {
        /* 忽略存储容量不足 */
      }
    },
    newChat() {
      this.activeId = ''
      this.newChatStrategy = false
      this.drafts[''] = ''
      this.persist()
    },
    switchTo(id: string) {
      if (!this.conversations.some((c) => c.id === id)) return
      this.activeId = id
      this.persist()
    },
    toggleStrategy() {
      if (this.activeRequest) return
      const conversation = this.conversations.find((c) => c.id === this.activeId)
      if (conversation) conversation.gameState = conversation.gameState === undefined ? {} : undefined
      else this.newChatStrategy = !this.newChatStrategy
      this.persist()
    },
    remove(id: string) {
      if (this.requests[id]) return
      this.conversations = this.conversations.filter((c) => c.id !== id)
      delete this.drafts[id]
      if (this.activeId === id) this.activeId = this.orderedConversations[0]?.id ?? ''
      this.persist()
    },
    async decideAudio(selectedBvids: string[]) {
      const request = this.activeRequest
      if (!request?.taskId || !request.audioConfirmation || request.confirmationBusy) return
      request.confirmationBusy = true
      request.confirmationError = ''
      try {
        await confirmAudio(request.taskId, selectedBvids)
        request.audioConfirmation = null
      } catch (error) {
        request.confirmationError = error instanceof Error ? error.message : '提交失败，请重试'
      } finally {
        request.confirmationBusy = false
      }
    },
    async togglePause() {
      const request = this.activeRequest
      if (!request?.taskId || request.pauseBusy) return
      request.pauseBusy = true
      request.pauseError = ''
      try {
        const task = await setTaskPaused(request.taskId, !request.pauseRequested)
        request.pauseRequested = task.pause_requested
        request.paused = task.paused
      } catch (error) {
        request.pauseError = error instanceof Error ? error.message : '操作失败'
      } finally {
        request.pauseBusy = false
      }
    },
    async ask(question: string, retry = false) {
      question = question.trim()
      if (!question || this.activeRequest) return
      if (!this.activeId) {
        const id = newId()
        const now = Date.now()
        this.conversations.push({
          id, title: '', messages: [], createdAt: now, updatedAt: now,
          gameState: this.newChatStrategy ? {} : undefined,
        })
        this.newChatStrategy = false
        this.activeId = id
      }

      const id = this.activeId
      const conversation = this.conversations.find((c) => c.id === id)!
      if (retry) conversation.messages.splice(-2)
      const history = conversation.messages
        .filter((m) => m.text.trim() && !m.error && !m.streaming)
        .slice(-MAX_HISTORY * 2)
        .map((m) => ({ role: m.role === 'q' ? 'user' as const : 'assistant' as const, content: m.text }))
      conversation.messages.push(
        { id: ++seq, role: 'q', text: question, citations: [] },
        { id: ++seq, role: 'a', text: '', citations: [], streaming: true },
      )
      conversation.title = titleOf(conversation.messages)
      conversation.updatedAt = Date.now()
      const answer = conversation.messages.at(-1)!
      this.requests[id] = newRequest()
      const request = this.requests[id]
      if (this.conversations.length > MAX_CONVERSATIONS) {
        const oldest = this.orderedConversations.reverse().find((c) => c.id !== id && !this.requests[c.id])
        if (oldest) {
          this.conversations = this.conversations.filter((c) => c.id !== oldest.id)
          delete this.drafts[oldest.id]
        }
      }
      this.persist()

      try {
        await streamAsk(question, {
          onTask: (taskId) => { request.taskId = taskId },
          onGameState: (state) => {
            conversation.gameState = state
            this.persist()
          },
          onPauseState: (paused) => { request.paused = paused },
          onAudioConfirmation: (confirmation) => { request.audioConfirmation = confirmation },
          onAudioImportOffer: (videos) => { answer.audioImportOptions = videos },
          onCitations: (citations) => { answer.citations = citations },
          onExternalSearch: (videos) => { answer.externalVideos = videos },
          onAgentStep: (step) => {
            const steps = answer.agentSteps ?? (answer.agentSteps = [])
            const index = steps.findIndex((item) => item.stage === step.stage)
            if (index >= 0) steps[index] = step
            else steps.push(step)
          },
          onDelta: (text) => { answer.text += text },
          onAnswerReplace: (text, citations) => {
            answer.text = text
            answer.citations = citations
          },
          onDone: (citations) => { answer.citations = citations },
        }, history, conversation.gameState)
      } catch (error) {
        answer.error = error instanceof Error ? error.message : '问答中断，请重试'
      } finally {
        answer.streaming = false
        delete this.requests[id]
        this.persist()
      }
    },
    retryLast() {
      const question = this.messages.at(-2)
      if (question?.role === 'q' && this.messages.at(-1)?.error) return this.ask(question.text, true)
    },
  },
})
