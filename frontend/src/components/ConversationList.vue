<script setup lang="ts">
import { Button } from '@/components/ui/button'
import type { Conversation } from '@/types'

defineProps<{
  conversations: Conversation[]
  activeId: string
  runningIds: string[]
}>()

const emit = defineEmits<{
  (e: 'new'): void
  (e: 'select', id: string): void
  (e: 'remove', id: string): void
}>()

function fmtTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  const y = new Date(now.getTime() - 864e5)
  if (d.toDateString() === y.toDateString()) return '昨天'
  return `${d.getMonth() + 1}-${d.getDate()}`
}
</script>

<template>
  <div class="conv">
    <Button class="new-btn" variant="outline" type="button" @click="emit('new')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 5v14M5 12h14" />
      </svg>
      新建对话
    </Button>

    <div class="scroll quiet-scroll">
      <div v-if="conversations.length" class="list-head">历史会话</div>
      <ul v-if="conversations.length" class="list">
        <li
          v-for="c in conversations"
          :key="c.id"
          class="item"
          :class="{ active: c.id === activeId }"
        >
          <Button class="select" variant="ghost" type="button" :aria-current="c.id === activeId ? 'true' : undefined" @click="emit('select', c.id)">
            <span class="title" :title="c.title">{{ c.title }}</span>
            <span class="time">{{ fmtTime(c.createdAt ?? c.updatedAt) }}</span>
            <span v-if="runningIds.includes(c.id)" class="running" aria-label="回答处理中" title="回答处理中"></span>
          </Button>
          <Button v-if="!runningIds.includes(c.id)" class="del" variant="ghost" size="icon-xs" type="button" aria-label="删除会话" @click="emit('remove', c.id)">×</Button>
        </li>
      </ul>
      <div v-else class="empty-hint">暂无历史会话</div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.conv {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  flex: 1;
  min-height: 0;
}
.new-btn {
  flex: none;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.55rem 0.75rem;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--panel);
  color: var(--ink);
  font-size: 0.85rem;
  font-weight: 600;
  transition: background 0.15s, border-color 0.15s;
}
.new-btn:hover:not(:disabled) {
  background: var(--sidebar-item-active);
}
.new-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.new-btn svg {
  width: 15px;
  height: 15px;
  color: var(--accent);
}
.scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: 0.2rem;
}
.list-head {
  font-size: 0.72rem;
  color: var(--ink-3);
  padding: 0 0.2rem 0.35rem;
}
.list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.item {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.08rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}
.select { display: flex; height: auto; flex-direction: column; align-items: flex-start; gap: .08rem; text-align: left; width: 100%; padding: .5rem 1.55rem .5rem .65rem; }
.select:hover { background: transparent; }
.running { position: absolute; right: .65rem; top: .72rem; width: .4rem; height: .4rem; border-radius: 50%; background: var(--accent); }
.item:hover {
  background: var(--sidebar-item-active);
}
.item.active {
  background: var(--sidebar-item-active);
}
.title {
  max-width: 100%;
  white-space: normal;
  font-size: 0.84rem;
  line-height: 1.4;
  color: var(--ink-2);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}
.item.active .title {
  color: var(--ink);
  font-weight: 600;
}
.time {
  font-size: 0.7rem;
  color: var(--ink-3);
}
.del {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  right: 0.2rem;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 0.9rem;
  line-height: 1;
  color: var(--ink-3);
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}
.item:hover .del,
.del:focus-visible,
.item.active .del {
  opacity: 1;
}
.del:hover {
  color: var(--ink);
  background: var(--line);
}
.empty-hint {
  font-size: 0.78rem;
  color: var(--ink-3);
  padding: 0.6rem 0.2rem;
}

@media (max-width: 760px) {
  .conv {
    flex-direction: row;
    align-items: center;
    height: auto;
    gap: 0.5rem;
  }
  .new-btn {
    padding: 0.35rem 0.6rem;
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .scroll {
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 0;
  }
  .list-head,
  .empty-hint {
    display: none;
  }
  .list {
    flex-direction: row;
    gap: 0.35rem;
  }
  .item {
    flex: none;
    max-width: 170px;
    border-radius: var(--radius-sm);
  }
  .select { padding: .3rem 1.25rem .3rem .6rem; }
  .running { right: .4rem; top: .65rem; }
  .title {
    -webkit-line-clamp: 1;
    font-size: 0.78rem;
    white-space: nowrap;
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .time,
  .del {
    display: none;
  }
}
</style>
