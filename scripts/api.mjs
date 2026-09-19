import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { generateApi } from 'swagger-typescript-api';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const check = process.argv.includes('--check');
const temporary = check ? await mkdtemp(path.join(tmpdir(), 'morgenruf-api-')) : null;

const spec = path.join(temporary ?? root, check ? 'openapi.json' : 'app/openapi.json');
const output = path.join(temporary ?? root, check ? 'generated' : 'frontend/src/common/api/generated');
const committedOutput = path.join(root, 'frontend/src/common/api/generated');

const python = process.env.PYTHON ?? (existsSync(path.join(root, '.venv/bin/python')) ? path.join(root, '.venv/bin/python') : 'python3');

try {
  const exported = spawnSync(python, ['-m', 'src.openapi', '--output', spec], {
    cwd: root,
    env: { ...process.env, PYTHONPATH: path.join(root, 'app') },
    stdio: 'inherit',
  });

  if (exported.error) {
    throw exported.error;
  }

  if (exported.status !== 0) {
    throw new Error('Backend OpenAPI export failed');
  }

  await mkdir(output, { recursive: true });
  await generateApi({
    input: spec,
    output,
    httpClientType: 'fetch',
    modular: true,
    moduleNameFirstTag: true,
    singleHttpClient: true,
    typeOnlyImports: true,
    extractRequestParams: true,
    extractRequestBody: true,
    extractResponseError: true,
    sortTypes: true,
    sortRoutes: true,
    cleanOutput: true,
  });

  if (check) {
    const drift = [];
    if ((await readFile(spec, 'utf8')) !== (await readFile(path.join(root, 'app/openapi.json'), 'utf8'))) {
      drift.push('app/openapi.json');
    }

    const names = new Set([...(await readdir(output)), ...(await readdir(committedOutput))]);

    for (const name of [...names].sort()) {
      const fresh = await readFile(path.join(output, name), 'utf8').catch(() => null);
      const existing = await readFile(path.join(committedOutput, name), 'utf8').catch(() => null);

      if (fresh !== existing) {
        drift.push(`frontend/src/common/api/generated/${name}`);
      }
    }

    if (drift.length) {
      throw new Error(`Generated API artifacts are stale. Run pnpm api:generate and commit:\n${drift.join('\n')}`);
    }

    console.log('OpenAPI and generated client are up to date.');
  }
} finally {
  if (temporary) await rm(temporary, { recursive: true, force: true });
}
