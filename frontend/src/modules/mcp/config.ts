export function buildMcpConfig(client: string, endpoint: string) {
  if (client === 'http') {
    const shellEndpoint = `'${endpoint.replaceAll("'", "'\\''")}'`;

    return `curl -X POST ${shellEndpoint} \\\n  -H 'Authorization: Bearer mrn_YOUR_KEY_HERE' \\\n  -H 'Content-Type: application/json' \\\n  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'`;
  }

  const server = {
    url: endpoint,
    headers: { Authorization: 'Bearer mrn_YOUR_KEY_HERE' },
  };

  return JSON.stringify(
    client === 'vscode'
      ? { servers: { morgenruf: { type: 'http', ...server } } }
      : { mcpServers: { morgenruf: server } },
    null,
    2,
  );
}
