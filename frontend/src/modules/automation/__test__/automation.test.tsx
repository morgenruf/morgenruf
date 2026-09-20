import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { chooseOption } from '@/test/select';

import AutomationPage from '../pages/automation-page';

const mock = vi.hoisted(() => ({ create: vi.fn() }));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: { team_id: 'T1', role: 'member', module_admin: ['standup'] },
  }),
}));

vi.mock('@/common/api/client', () => ({
  api: {
    automation: {
      listRules: vi.fn().mockResolvedValue({ data: [] }),
      createRule: mock.create,
      deleteRule: vi.fn(),
    },
    workspace: {
      listChannels: vi
        .fn()
        .mockResolvedValue({ data: [{ id: 'C1', name: 'design' }] }),
    },
  },
}));

beforeEach(() => {
  vi.clearAllMocks();

  mock.create.mockResolvedValue({ data: { id: 2 } });
});

it('keeps the low participation default and clears a channel target when changing action', async () => {
  const user = userEvent.setup();

  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <AutomationPage />
    </QueryClientProvider>,
  );

  await user.click(
    screen.getByRole('button', { name: /Notice a quiet standup/ }),
  );

  expect(screen.getByLabelText('Participation threshold (%)')).toHaveValue(50);

  await chooseOption(user, 'Slack channel', '#design');
  await chooseOption(user, 'Action', 'Send direct message');

  expect(screen.getByLabelText('Slack user ID')).toHaveValue('');

  await user.type(screen.getByLabelText('Slack user ID'), 'U1');
  await chooseOption(user, 'Action', 'Post to channel');
  expect(
    screen.getByRole('combobox', { name: 'Slack channel' }),
  ).toHaveTextContent('Choose a channel');
  await chooseOption(user, 'Slack channel', '#design');
  await chooseOption(user, 'Action', 'Send direct message');
  expect(screen.getByLabelText('Slack user ID')).toHaveValue('');
  await user.type(screen.getByLabelText('Slack user ID'), 'U2');
  await user.click(screen.getByRole('button', { name: 'Save rule' }));

  await waitFor(() =>
    expect(mock.create).toHaveBeenCalledWith(
      expect.objectContaining({
        condition_value: '50',
        trigger: 'low_participation',
        action: 'send_dm',
        action_target: 'U2',
      }),
    ),
  );
});

it('updates trigger-dependent fields and resets selects when reopening from a template', async () => {
  const user = userEvent.setup();
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <AutomationPage />
    </QueryClientProvider>,
  );
  await user.click(
    screen.getByRole('button', { name: /Notice a quiet standup/ }),
  );
  expect(screen.getByRole('combobox', { name: 'Trigger' })).toHaveTextContent(
    'Low participation',
  );
  await chooseOption(user, 'Trigger', 'Standup complete');
  expect(
    screen.queryByLabelText('Participation threshold (%)'),
  ).not.toBeInTheDocument();
  await chooseOption(user, 'Action', 'Call webhook');
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  await user.click(
    screen.getByRole('button', { name: /Notice a quiet standup/ }),
  );
  expect(screen.getByRole('combobox', { name: 'Trigger' })).toHaveTextContent(
    'Low participation',
  );
  expect(screen.getByRole('combobox', { name: 'Action' })).toHaveTextContent(
    'Post to channel',
  );
  expect(
    screen.getByRole('combobox', { name: 'Slack channel' }),
  ).toHaveTextContent('Choose a channel');
  expect(screen.getByLabelText('Participation threshold (%)')).toHaveValue(50);
});
