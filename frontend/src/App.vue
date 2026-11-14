<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from '@/components/Sidebar.vue'
import { useChatStore } from '@/stores/chat'

const route = useRoute()
const chat = useChatStore()
onMounted(() => chat.restore())
/** 问答页占满可视高度：对话区滚动，输入框贴底 */
const isChat = computed(() => route.name === 'ask')
</script>

<template>
  <div class="app">
    <Sidebar />
    <main class="main quiet-scroll" :class="{ 'main-chat': isChat }">
      <div class="wrap" :class="{ 'wrap-chat': isChat }">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<style lang="scss" scoped>
.app {
  display: flex;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}
.main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 2.2rem 1.6rem;
  display: flex;
  justify-content: center;
  overflow-y: auto;
}
/* 问答页不整页滚动，交给内部对话区 */
.main-chat {
  overflow: hidden;
  padding: 0;
}
.wrap {
  width: 100%;
  max-width: 1120px;
}
.wrap-chat {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  max-width: none;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.fade-leave-to {
  opacity: 0;
}
@media (max-width: 760px) {
  .app {
    flex-direction: column;
    height: 100dvh;
  }
  .main {
    padding: 1rem 1rem 1.2rem;
  }
  .main-chat { padding: 0; }
}
</style>
