import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Standup } from '@/common/api/generated/data-contracts';
import { chooseOption } from '@/test/select';

import { StandupsPage } from './pages';

const mock = vi.hoisted(() => ({
  editable: true,
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  channels: vi.fn(),
  members: vi.fn(),
  templates: vi.fn(),
  analytics: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
  usePermissions: () => ({
    isAdmin: mock.editable,
    canAdminister: () => mock.editable,
  }),
}));

vi.mock('@/common/api/client', () => ({
  api: {
    standups: {
      listStandups: mock.list,
      createStandup: mock.create,
      updateStandup: mock.update,
      deleteStandup: vi.fn(),
      listTemplates: mock.templates,
    },
    workspace: { listChannels: mock.channels },
    members: { listMembers: mock.members },
    analytics: { getAnalytics: mock.analytics },
  },
}));

const standup: Standup = {
  id: 7,
  name: 'Design daily',
  channel_id: 'C1',
  schedule_time: '09:00',
  schedule_tz: 'UTC',
  schedule_days: ['mon', 'wed'],
  questions: ['What is next?'],
  participants: [],
  active: true,
  reminder_minutes: 0,
  report_channel: '',
  digest_email: '',
  digest_enabled: false,
  nudge_missing: false,
  nudge_minutes_before: 20,
  report_time: '',
  group_by: 'member',
  post_as: 'combined',
  sort_order: 'chronological',
  edit_window: 'report',
  display_avatar: true,
  jira_base_url: '',
  zendesk_base_url: '',
  github_repo: '',
  linear_team: '',
  ai_summary_enabled: false,
  ai_provider: 'openai',
  feed_token: '',
  feed_public: false,
  manager_email: '',
  manager_digest_enabled: false,
  post_to_thread: false,
  notify_on_report: true,
  post_summary: true,
  registration_error: null,
  next_run: '',
};

function view(path = '/dashboard/standups') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <StandupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return client;
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.editable = true;
  mock.list.mockResolvedValue({ data: [standup] });
  mock.channels.mockResolvedValue({ data: [{ id: 'C1', name: 'design' }] });
  mock.members.mockResolvedValue({ data: [{ id: 'U1', name: 'Mina' }] });
  mock.templates.mockResolvedValue({
    data: [
      {
        id: 'retro',
        name: 'Retrospective',
        description: 'Reflect together',
        icon: '☀',
        questions: ['What worked?'],
      },
    ],
  });
  mock.analytics.mockResolvedValue({ data: { schedules: [] } });
  mock.create.mockResolvedValue({ data: standup });
  mock.update.mockResolvedValue({ data: standup });
});

describe('standup management', () => {
  it('shows whole-channel enrollment and hides mutations for read-only members', async () => {
    mock.editable = false;

    view();

    expect(await screen.findByText('Design daily')).toBeInTheDocument();
    expect(screen.getByText('Everyone in the channel')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Edit' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'New standup' }),
    ).not.toBeInTheDocument();
  });

  it('uses a template and sends summary fields through the generated client', async () => {
    const user = userEvent.setup();
    const client = view('/dashboard/standups?edit=7');

    await screen.findByRole('dialog');
    expect(
      screen.getByRole('combobox', { name: 'Channel' }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Schedule' }));
    await user.click(screen.getByRole('button', { name: 'Use a template' }));
    await user.click(
      await screen.findByRole('button', { name: /Retrospective/ }),
    );

    expect(screen.getByLabelText('Question 1')).toHaveValue('What worked?');

    await user.click(screen.getByRole('tab', { name: 'Summary' }));
    await user.type(
      screen.getByLabelText(/Daily email to/),
      'lead@example.com',
    );
    await user.click(screen.getByLabelText('Send that email daily'));

    const invalidate = vi.spyOn(client, 'invalidateQueries');
    await user.click(screen.getByRole('button', { name: 'Save standup' }));

    await waitFor(() =>
      expect(mock.update).toHaveBeenCalledWith(
        { standupId: 7 },
        expect.objectContaining({
          questions: ['What worked?'],
          digest_email: 'lead@example.com',
          digest_enabled: true,
          participants: [],
        }),
      ),
    );
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: ['workspace', 'T1', 'analytics'],
      }),
    );
  });

  it('keeps a failed save open and displays the backend validation message', async () => {
    mock.update.mockRejectedValue({
      error: { error: 'The channel is unavailable.' },
    });
    const user = userEvent.setup();

    view('/dashboard/standups?edit=7');
    await screen.findByRole('dialog');

    await user.click(screen.getByRole('button', { name: 'Save standup' }));

    expect(
      await screen.findByText('The channel is unavailable.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('reports query failure instead of claiming there are no schedules', async () => {
    mock.list.mockRejectedValue(new Error('Connection interrupted'));

    view();

    expect(
      await screen.findByText('Connection interrupted'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Your first standup starts here'),
    ).not.toBeInTheDocument();
  });
});

it('requires a channel and focuses its trigger when validation fails', async () => {
  const user = userEvent.setup();
  view();
  await screen.findByText('Design daily');
  await user.click(screen.getByRole('button', { name: 'New standup' }));
  const channel = screen.getByRole('combobox', {
    name: 'Channel',
  });
  expect(channel).toHaveTextContent('Choose a channel…');
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  expect(await screen.findByText('Choose a channel.')).toBeInTheDocument();
  expect(channel).toHaveAttribute('aria-invalid', 'true');
  await waitFor(() => expect(channel).toHaveFocus());
  // React Hook Form schedules a second focus pass after invalid submission.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(mock.create).not.toHaveBeenCalled();
  await chooseOption(user, 'Channel', '#design');
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  await waitFor(() =>
    expect(mock.create).toHaveBeenCalledWith(
      expect.objectContaining({ channel_id: 'C1' }),
    ),
  );
});

it.each([
  ['The weekend (~2.5 days)', -1],
  ['No reminder', 0],
])(
  'saves numeric reminder %s and resets the report channel to its empty value',
  async (label, minutes) => {
    mock.list.mockResolvedValue({
      data: [{ ...standup, reminder_minutes: 30, report_channel: 'C1' }],
    });
    const user = userEvent.setup();
    view('/dashboard/standups?edit=7');
    await screen.findByRole('dialog');
    await waitFor(() =>
      expect(
        screen.getByRole('combobox', { name: 'Channel' }),
      ).toHaveTextContent('#design'),
    );
    await user.click(screen.getByRole('tab', { name: 'Schedule' }));
    expect(
      screen.getByRole('combobox', {
        name: 'Remind participants before standup',
      }),
    ).toHaveTextContent('30 minutes');
    await chooseOption(user, 'Remind participants before standup', label);
    await user.click(screen.getByRole('tab', { name: 'Summary' }));
    expect(
      screen.getByRole('combobox', { name: 'Report channel' }),
    ).toHaveTextContent('#design');
    await chooseOption(user, 'Report channel', 'Same as standup channel');
    await user.click(screen.getByRole('tab', { name: 'Advanced' }));
    await chooseOption(user, 'Group report by', 'Question');
    await chooseOption(user, 'Edit window', '4 hours');
    await chooseOption(user, 'AI provider', 'Anthropic');
    await user.click(screen.getByRole('button', { name: 'Save standup' }));
    await waitFor(() =>
      expect(mock.update).toHaveBeenCalledWith(
        { standupId: 7 },
        expect.objectContaining({
          reminder_minutes: minutes,
          report_channel: '',
          group_by: 'question',
          edit_window: '4h',
          ai_provider: 'anthropic',
        }),
      ),
    );
  },
  15_000,
);
