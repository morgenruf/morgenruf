import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import WebhooksPage from '../pages/webhooks-page';

const mock = vi.hoisted(() => ({
  admin: true,
  rotate: vi.fn(),
  deliveries: vi.fn(),
  test: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: {
      team_id: 'T1',
      role: mock.admin ? 'admin' : 'member',
      module_admin: ['standup'],
    },
  }),
}));

vi.mock('@/common/api/client', () => ({
  api: {
    webhooks: {
      listWebhooks: vi.fn().mockResolvedValue({
        data: [
          {
            id: 5,
            url: 'https://example.com/hook',
            events: ['standup.completed'],
            signed: true,
            secret_prefix: 'whk_',
            created_at: '2026-09-18T10:00:00Z',
          },
        ],
      }),
      getWebhookEvents: vi.fn().mockResolvedValue({
        data: {
          events: ['standup.completed'],
          default: ['standup.completed'],
        },
      }),
      createWebhook: vi.fn(),
      updateWebhook: vi.fn(),
      deleteWebhook: vi.fn(),
      rotateWebhookSecret: mock.rotate,
      listWebhookDeliveries: mock.deliveries,
      testWebhook: mock.test,
    },
  },
}));

function view() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <WebhooksPage />
    </QueryClientProvider>,
  );

  return client;
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.admin = true;
  mock.rotate.mockResolvedValue({ data: { id: 5, secret: 'whk_only_once' } });
  mock.deliveries.mockResolvedValue({ data: [] });
  mock.test.mockResolvedValue({
    data: { ok: false, status_code: 500, error: 'Receiver failed' },
  });
});

it('requires a confirmation to rotate and keeps the returned secret out of cached results', async () => {
  const user = userEvent.setup({ delay: null });
  const client = view();

  await user.click(
    await screen.findByRole('button', { name: 'Rotate secret' }),
  );

  expect(mock.rotate).not.toHaveBeenCalled();

  const buttons = screen.getAllByRole('button', { name: 'Rotate secret' });
  await user.click(buttons[buttons.length - 1]);

  expect(await screen.findByTestId('one-time-secret')).toHaveTextContent(
    'whk_only_once',
  );
  expect(
    JSON.stringify(
      client
        .getQueryCache()
        .getAll()
        .map((query) => query.state.data),
    ),
  ).not.toContain('whk_only_once');
  expect(
    client
      .getMutationCache()
      .getAll()
      .every((mutation) => mutation.state.data === undefined),
  ).toBe(true);

  await user.click(screen.getByRole('button', { name: 'Done' }));

  await waitFor(() =>
    expect(screen.queryByTestId('one-time-secret')).not.toBeInTheDocument(),
  );
});

it('allows read-only delivery inspection without workspace administration actions', async () => {
  mock.admin = false;
  const user = userEvent.setup({ delay: null });

  view();
  await screen.findByText('https://example.com/hook');
  expect(
    screen.queryByRole('button', { name: 'Add webhook' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Send test event' }),
  ).not.toBeInTheDocument();
  expect(mock.deliveries).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: 'Deliveries' }));

  expect(
    await screen.findByText('No deliveries recorded yet'),
  ).toBeInTheDocument();
});
