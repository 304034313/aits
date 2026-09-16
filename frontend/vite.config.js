import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const sonicProxyTarget = env.VITE_SONIC_PROXY_TARGET || 'http://127.0.0.1:5000'

  return {
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  define: {
    // 为 Monaco Editor 配置全局变量
    global: 'globalThis',
  },
  optimizeDeps: {
    include: ['monaco-editor']
  },
  assetsInclude: ['**/*.worker.js'],
  server: {
    port: 5173,
	host: '0.0.0.0',// 韬哥加！！
    proxy: {
      '/api/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Django MEDIA（压测 CSV、Allure 等）；开发时链接常为 /media/... 会打到 5173，需转发到后端
      '/media': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Playwright报告静态文件代理
      '/playwright-reports': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // WebSocket代理配置
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true, // 启用WebSocket代理
        changeOrigin: true,
      },
      '/sonic-api': {
        target: sonicProxyTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/sonic-api/, '/server/api'),
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
  },
}
})
