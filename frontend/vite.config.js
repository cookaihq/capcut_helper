import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3176,
    proxy: {
      // 开发期把 /api 代理到本地后端（后端默认端口 9527）
      '/api': 'http://127.0.0.1:9527',
    },
  },
  build: {
    outDir: 'dist',
  },
  test: {
    environment: 'jsdom',
  },
})
