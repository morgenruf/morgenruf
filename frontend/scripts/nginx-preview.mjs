import { spawn, spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const port = process.env.MORGENRUF_PREVIEW_PORT ?? '4173';
const backend = process.env.BACKEND_URL ?? 'http://host.docker.internal:3006';
const image = 'morgenruf-frontend:preview';
const container = `morgenruf-preview-${randomUUID()}`;

let child;
let stopping = false;

function stop() {
  if (stopping) return;

  stopping = true;
  spawnSync('docker', ['rm', '--force', container], { stdio: 'ignore' });
  child?.kill('SIGTERM');
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    stop();
    process.exit(0);
  });
}

process.on('exit', stop);

function run(args) {
  return new Promise((resolve, reject) => {
    child = spawn('docker', args, { cwd: root, stdio: 'inherit' });
    child.once('error', reject);
    child.once('exit', (code, signal) => {
      child = undefined;

      if (code === 0 || stopping) resolve();
      else reject(new Error(`docker ${args[0]} exited with ${code ?? signal}`));
    });
  });
}

try {
  // The production Dockerfile builds from source without a backend or credentials.
  await run(['build', '--file', 'frontend/Dockerfile', '--tag', image, '.']);
  console.log(`Preview: http://127.0.0.1:${port}/dashboard/`);
  await run([
    'run',
    '--rm',
    '--name',
    container,
    '--publish',
    `127.0.0.1:${port}:8080`,
    '--add-host',
    'host.docker.internal:host-gateway',
    '--env',
    `BACKEND_URL=${backend}`,
    image,
  ]);
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
