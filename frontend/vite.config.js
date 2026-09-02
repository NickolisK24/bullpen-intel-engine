import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ROUTE_ENTRY_METADATA } from './src/utils/publicRouteMetadata.js'
import { writeRouteEntryPages } from './scripts/generate-route-entry-pages.mjs'

const root = fileURLToPath(new URL('.', import.meta.url))
const routeEntries = Object.fromEntries(
  ROUTE_ENTRY_METADATA.map(entry => [
    `route-${entry.key}`,
    resolve(root, `route-entry/${entry.key}.html`),
  ]),
)

export default defineConfig(async ({ command }) => {
  if (command === 'build') {
    await writeRouteEntryPages()
  }
  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        input: {
          main: resolve(root, 'index.html'),
          ...routeEntries,
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:5000',
          changeOrigin: true,
        },
      },
    },
  }
})
