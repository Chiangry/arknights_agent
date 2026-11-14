import { createRouter, createWebHashHistory } from 'vue-router'
import LibraryView from '@/views/LibraryView.vue'
import ChatView from '@/views/ChatView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', alias: '/ask', name: 'ask', component: ChatView, meta: { title: '问答' } },
    { path: '/add', name: 'add', component: LibraryView, meta: { title: '添加视频' } },
  ],
})

export default router
