import { defineStore } from 'pinia'
import { fetchVideos } from '@/api/videos'
import type { Video } from '@/types'

export const useVideosStore = defineStore('videos', {
  state: () => ({
    list: [] as Video[],
    loading: false,
    error: '',
  }),
  getters: {
    totalChunks: (s) => s.list.reduce((n, v) => n + v.chunk_count, 0),
  },
  actions: {
    async load() {
      this.loading = true
      this.error = ''
      try {
        this.list = await fetchVideos()
      } catch (error) {
        this.error = error instanceof Error ? error.message : '无法加载视频库'
      } finally {
        this.loading = false
      }
    },
  },
})
