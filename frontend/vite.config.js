import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { env } from 'node:process'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ['vitest'] },
  test: { include: ['../qa_tests/frontend/**/*.test.js'] },
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': {
        target: env.BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-charts': ['recharts'],
          'vendor-query': ['@tanstack/react-query', 'axios'],
        }
      }
    }
  }
})
