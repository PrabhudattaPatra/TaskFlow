import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api (REST + WebSocket) to FastAPI so the refresh cookie is same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', ws: true, changeOrigin: true },
    },
  },
})
