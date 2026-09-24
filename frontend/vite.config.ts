import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import { tanstackStart } from '@tanstack/react-start/plugin/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

import { backendProxyPatterns } from './config/backend-routes';

const target = process.env.API_PROXY_TARGET || 'http://localhost:3006';

export default defineConfig({
  plugins: [
    tanstackStart({
      spa: { enabled: true },
      router: { routeFileIgnorePattern: '__test__' },
    }),
    react(),
    tailwindcss(),
  ],

  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },

  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (/\/node_modules\/(react|react-dom|scheduler)\//.test(id))
              return 'react-vendor';

            if (id.includes('/@tanstack/react-query/')) return 'query-vendor';

            if (id.includes('/@base-ui/') || id.includes('/@floating-ui/'))
              return 'ui-vendor';
          }
        },
      },
    },
  },

  // Start uses a preview server to prerender the neutral SPA shell during build.
  preview: { host: '127.0.0.1' },

  server: {
    port: 5173,
    allowedHosts: process.env.MORGENRUF_DEV_APP_URL
      ? [new URL(process.env.MORGENRUF_DEV_APP_URL).hostname]
      : undefined,
    proxy: Object.fromEntries(
      backendProxyPatterns.map((path) => [
        path,
        { target, changeOrigin: false },
      ]),
    ),
  },
});
