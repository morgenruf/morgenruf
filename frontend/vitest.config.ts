import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // These are full render-and-interact tests driving Base UI selects through
    // portals, so the slowest run for a couple of seconds locally and several
    // times that on a loaded CI runner. The 5s default left no room for that.
    testTimeout: 20000,
    hookTimeout: 20000,
  },
});
