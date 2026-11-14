<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import ConversationList from '@/components/ConversationList.vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
const route = useRoute()
const router = useRouter()

function openConversation(id?: string) {
  if (id) chat.switchTo(id)
  else chat.newChat()
  if (route.name !== 'ask') void router.push({ name: 'ask' })
}
</script>

<template>
  <aside class="sidebar" aria-label="工作区侧栏">
    <div class="sidebar-top">
      <RouterLink :to="{ name: 'ask' }" class="brand" aria-label="视知首页">
        <span class="mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none"><path d="M9 6.5v11l8.5-5.5z" fill="currentColor" /></svg>
        </span>
        <span>视知</span>
      </RouterLink>
      <nav class="nav" aria-label="工作区功能">
        <Button as-child variant="ghost" size="sm">
          <RouterLink :to="{ name: 'ask' }" class="nav-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" aria-hidden="true">
              <path d="M20 11.5a8 8 0 0 1-8 8H4l1.5-4A8 8 0 1 1 20 11.5Z" />
            </svg>
            问答
          </RouterLink>
        </Button>
        <Button as-child variant="ghost" size="sm">
          <RouterLink :to="{ name: 'add' }" class="nav-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" aria-hidden="true">
              <rect x="4" y="5" width="16" height="14" rx="2" /><path d="m10 9 5 3-5 3z" />
            </svg>
            视频库
          </RouterLink>
        </Button>
      </nav>
    </div>
    <ConversationList
      :conversations="chat.orderedConversations"
      :active-id="route.name === 'ask' ? chat.activeId : ''"
      :running-ids="chat.runningIds"
      @new="openConversation()"
      @select="openConversation"
      @remove="chat.remove"
    />
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--rail-width);
  min-height: 0;
  flex: none;
  display: flex;
  flex-direction: column;
  padding: 1rem .75rem;
  background: var(--sidebar);
  border-right: 1px solid var(--line);
}
.sidebar-top { flex: none; padding-bottom: .85rem; }
.brand { display: flex; align-items: center; width: fit-content; gap: .55rem; padding: .15rem .4rem .9rem; font-size: .97rem; font-weight: 700; }
.mark { display: grid; place-items: center; width: 27px; height: 27px; border-radius: 8px; color: #12303a; background: var(--accent); }
.mark svg { width: 16px; height: 16px; }
.nav { display: flex; flex-direction: column; gap: .25rem; }
.nav-item { display: flex; align-items: center; justify-content: flex-start; gap: .55rem; height: 34px; padding: 0 .6rem; border-radius: 7px; color: var(--ink-2); font-size: .81rem; white-space: nowrap; }
.nav-item svg { width: 16px; height: 16px; color: var(--accent); }
.nav-item:hover { color: var(--ink); background: var(--sidebar-item-active); }
.nav-item.router-link-exact-active { color: var(--ink); background: var(--sidebar-item-active); font-weight: 650; }
@media (max-width: 760px) {
  .sidebar { width: 100%; border-right: 0; border-bottom: 1px solid var(--line); padding: .5rem .75rem; }
  .sidebar-top { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding-bottom: .4rem; }
  .brand { padding: 0; }
  .nav-item { height: 28px; padding-inline: .55rem; }
}
</style>
