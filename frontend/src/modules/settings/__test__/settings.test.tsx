import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TestRouter } from '@/test/router';

import { SettingsPage } from '../pages';

const mock = vi.hoisted(() => ({
  isAdmin: false,
  list: vi.fn(),
  modules: vi.fn(),
  update: vi.fn(),
  feed: vi.fn(),
  toggleModule: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
  usePermissions: () => ({
    isAdmin: mock.isAdmin,
    canAdminister: (name: string) => name === 'standup',
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    standups: { listStandups: mock.list, updateStandup: mock.update },
    workspace: {
      listModules: mock.modules,
      updateModule: mock.toggleModule,
      createFeedToken: mock.feed,
      deleteFeedToken: vi.fn(),
    },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

function view() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <TestRouter routeId="/dashboard/_authenticated/settings">
        <SettingsPage />
      </TestRouter>
    </QueryClientProvider>,
  );

  return client;
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.isAdmin = false;
  mock.list.mockResolvedValue({
    data: [
      {
        id: 9,
        name: 'Daily',
        schedule_time: '09:00',
        schedule_tz: 'UTC',
        schedule_days: ['mon'],
        participants: [],
        active: true,
        manager_email: 'lead@example.com',
        manager_digest_enabled: false,
        feed_public: false,
        feed_token: '',
      },
    ],
  });
  mock.modules.mockResolvedValue({
    data: [
      { name: 'connect', available: true, active: true, missing_scopes: [] },
    ],
  });
  mock.update.mockResolvedValue({ data: {} });
  mock.feed.mockResolvedValue({ data: { token: 'token', url: '/feed/token' } });
});

describe('workspace settings permissions', () => {
  it('lets a standup admin manage digests without publishing the feed or toggling modules', async () => {
    const user = userEvent.setup({ delay: null });

    view();

    expect(await screen.findByText('Manager digest')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(
      screen.getByText('Only workspace administrators can publish the feed.'),
    ).toBeInTheDocument();

    await user.click(screen.getByLabelText('Send a daily digest'));
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(mock.update).toHaveBeenCalledWith(
        { standupId: 9 },
        { manager_email: 'lead@example.com', manager_digest_enabled: true },
      ),
    );
  });

  it('invalidates workspace settings after a workspace admin publishes the feed', async () => {
    mock.isAdmin = true;
    const user = userEvent.setup({ delay: null });

    const client = view();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    await user.click(
      await screen.findByRole('switch', {
        name: 'Public standup feed enabled',
      }),
    );

    await waitFor(() => expect(mock.feed).toHaveBeenCalledOnce());
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ['workspace', 'T1', 'standups'],
    });
  });
});
