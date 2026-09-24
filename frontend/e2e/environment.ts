export const backendPort = process.env.MORGENRUF_E2E_BACKEND_PORT ?? '3008';
export const backend = `http://127.0.0.1:${backendPort}`;

export const productionBackendPort =
  process.env.MORGENRUF_E2E_BACKEND_PORT ?? '3009';
export const productionBackend = `http://127.0.0.1:${productionBackendPort}`;
