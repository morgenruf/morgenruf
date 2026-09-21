export const backendPort = process.env.MORGENRUF_E2E_BACKEND_PORT ?? '3008';
export const backend = `http://127.0.0.1:${backendPort}`;
