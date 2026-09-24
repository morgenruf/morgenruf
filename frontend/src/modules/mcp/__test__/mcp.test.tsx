import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { buildMcpConfig } from '../config';
import McpPage from '../pages/mcp-page';

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: {
      team_id: 'T1',
      role: 'admin',
      mcp_endpoint: 'https://morgenruf.example/mcp',
    },
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    mcp: {
      listKeys: vi.fn().mockResolvedValue({
        data: {
          keys: [
            {
              id: 1,
              name: 'Old assistant',
              key_prefix: 'mrn_old',
              active: false,
              created_at: '2026-09-18',
              last_used_at: null,
            },
          ],
        },
      }),
      createKey: vi.fn(),
      revokeKey: vi.fn(),
    },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

it('marks revoked keys and does not offer to revoke them again', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <McpPage />
    </QueryClientProvider>,
  );

  expect(await screen.findByText('Revoked')).toBeInTheDocument();
  expect(screen.getByText('Never')).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Revoke' }),
  ).not.toBeInTheDocument();

  const user = userEvent.setup({ delay: null });
  const assistant = screen.getByRole('combobox', { name: 'Assistant' });
  expect(assistant).toHaveTextContent('Claude Desktop');

  await user.click(assistant);
  await user.click(await screen.findByRole('option', { name: 'HTTP / curl' }));

  expect(assistant).toHaveTextContent('HTTP / curl');
  expect(
    screen.getByText('Run in a terminal to list available tools.'),
  ).toBeInTheDocument();
  expect(screen.getByText(/curl -X POST/)).toBeInTheDocument();
});

it('builds HTTP and editor configurations with scoped placeholder credentials', () => {
  const endpoint = 'https://morgenruf.example/mcp';

  expect(buildMcpConfig('http', endpoint)).toContain(
    `curl -X POST '${endpoint}'`,
  );
  expect(buildMcpConfig('http', endpoint)).toContain('"method":"tools/list"');

  const editor = JSON.parse(buildMcpConfig('vscode', endpoint));

  expect(editor.servers.morgenruf).toEqual({
    type: 'http',
    url: endpoint,
    headers: { Authorization: 'Bearer mrn_YOUR_KEY_HERE' },
  });
});
