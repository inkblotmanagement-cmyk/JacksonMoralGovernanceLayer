/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API paths are proxied to the backend so the browser stays same-origin.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  const proxy = { '/v1': target, '/healthz': target, '/readyz': target }
  return {
    plugins: [react()],
    build: { sourcemap: false, target: 'es2022' },
    server: { port: 5173, proxy },
    preview: { port: 4173, proxy },
    test: { environment: 'jsdom' },
  }
})
