import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

import pkg from './package.json' with { type: 'json' }

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [react(), tailwindcss()],
    // Sent with browser error reports, so they can be matched to a release.
    define: { 'import.meta.env.VITE_APP_VERSION': JSON.stringify(pkg.version) },
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, 'src') },
    },
    server: {
      port: 5173,
      host: true,
      // Same-origin proxy so the httpOnly refresh cookie works without CORS.
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true, ws: true },
      },
    },
    build: {
      sourcemap: false,
      chunkSizeWarningLimit: 700,
      rolldownOptions: {
        output: {
          // React (needed on every page) in its own file: it rarely changes, so browsers keep it cached across
          // deploys and only the app's own code is downloaded again after a release. Other libraries stay in the
          // lazily loaded page files (a catch-all vendor group pulled the chart library into the first load).
          // Packaging only; no code changes.
          advancedChunks: {
            groups: [{ name: 'react', test: /node_modules[\\/](react|react-dom|scheduler|react-router)[\\/]/ }],
          },
        },
      },
    },
  }
})
