import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

import { backend } from './e2e/environment';

const directory = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(directory, '..');
const localPython = path.join(root, '.venv/bin/python');
const python =
  process.env.PYTHON ?? (existsSync(localPython) ? localPython : 'python3');

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // The chart matrix renders a full analytics page per viewport, theme and
  // motion preference, and the slowest of those runs for about 40s. The 30s
  // default only passed in CI because the retry hid it, so these failed
  // locally where there is no retry.
  timeout: 90_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `"${python}" "${path.join(directory, 'e2e/backend.py')}"`,
      url: `${backend}/__test__/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'pnpm exec vite --host 127.0.0.1 --port 5174 --strictPort',
      url: 'http://127.0.0.1:5174',
      env: { API_PROXY_TARGET: backend },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
