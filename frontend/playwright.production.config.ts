import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

import {
  productionBackend as backend,
  productionBackendPort as backendPort,
} from './e2e/environment';

const directory = path.dirname(fileURLToPath(import.meta.url));
const localPython = path.resolve(directory, '../.venv/bin/python');
const python =
  process.env.PYTHON ?? (existsSync(localPython) ? localPython : 'python3');
const origin = 'http://127.0.0.1:5175';

export default defineConfig({
  testDir: './e2e/production',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60_000,
  outputDir: 'test-results-production',

  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report-production' }],
  ],

  use: {
    baseURL: origin,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [{ name: 'nginx-chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: [
    {
      command: `"${python}" "${path.join(directory, 'e2e/backend.py')}"`,
      url: `${backend}/__test__/health`,
      env: {
        MORGENRUF_E2E_APP_URL: origin,
        MORGENRUF_E2E_BACKEND_HOST: '0.0.0.0',
        MORGENRUF_E2E_BACKEND_PORT: backendPort,
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },

    {
      command: 'node scripts/nginx-preview.mjs',
      url: `${origin}/frontend-healthz`,
      env: {
        MORGENRUF_PREVIEW_PORT: '5175',
        BACKEND_URL: `http://host.docker.internal:${backendPort}`,
      },
      reuseExistingServer: false,
      timeout: 600_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 10_000 },
    },
  ],
});
