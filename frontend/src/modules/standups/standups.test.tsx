import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Standup } from '@/common/api/generated/data-contracts';
import { deferred } from '@/test/deferred';
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

const workspaceSettings = {
  edit_window: '4h',
  jira_base_url: 'https://team.atlassian.net',
  github_repo: 'team/project',
  linear_team: 'ENG',
  ai_summary_enabled: true,
  ai_provider: 'anthropic',
};

it.each([
  ['Summary', 'Daily email to', 'bad-address', 'lead@example.com'],
  ['Advanced', 'Jira base URL', 'bad-url', 'https://team.atlassian.net'],
  [
    'Summary',
    'Remind missing participants before report (minutes)',
    '21',
    '25',
  ],
])(
  'reveals and focuses the invalid %s field %s before saving',
  async (tab, label, invalid, valid) => {
    const user = userEvent.setup();
    view('/dashboard/standups?edit=7');
    await screen.findByRole('dialog');
    await user.click(screen.getByRole('tab', { name: tab }));
    const input = screen.getByLabelText(label);
    await user.clear(input);
    await user.type(input, invalid);
    await user.click(screen.getByRole('tab', { name: 'Basics' }));
    await user.click(screen.getByRole('button', { name: 'Save standup' }));

    await waitFor(() => expect(input).toBeVisible());
    expect(input).toHaveFocus();
    expect(screen.getByRole('alert')).toHaveTextContent(
      (input as HTMLInputElement).validationMessage,
    );
    expect(mock.update).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, valid);
    await user.click(screen.getByRole('button', { name: 'Save standup' }));
    await waitFor(() => expect(mock.update).toHaveBeenCalledOnce());
  },
);

it('loads shared settings before opening a new standup and leaves them unchanged on save', async () => {
  let resolveStandups!: (value: { data: Standup[] }) => void;
  mock.list.mockReturnValue(
    new Promise((resolve) => {
      resolveStandups = resolve;
    }),
  );
  const user = userEvent.setup();
  view('/dashboard/standups?new=true');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await act(async () =>
    resolveStandups({ data: [{ ...standup, ...workspaceSettings }] }),
  );
  await screen.findByRole('dialog');
  await chooseOption(user, 'Channel', '#design');
  await user.click(screen.getByRole('tab', { name: 'Advanced' }));
  expect(
    screen.getByRole('combobox', { name: 'Edit window' }),
  ).toHaveTextContent('4 hours');
  expect(screen.getByLabelText('Jira base URL')).toHaveValue(
    workspaceSettings.jira_base_url,
  );
  expect(screen.getByLabelText('GitHub repository')).toHaveValue(
    workspaceSettings.github_repo,
  );
  expect(screen.getByLabelText('Linear team prefix')).toHaveValue('ENG');
  expect(
    screen.getByRole('combobox', { name: 'AI provider' }),
  ).toHaveTextContent('Anthropic');
  expect(
    screen.getByLabelText('Enable AI-generated daily summary'),
  ).toBeChecked();
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  await waitFor(() => expect(mock.create).toHaveBeenCalled());
  const payload = mock.create.mock.calls[0][0];
  for (const field of Object.keys(workspaceSettings)) {
    expect(payload).not.toHaveProperty(field);
  }
});

it('does not overwrite shared settings when creating the first remaining standup', async () => {
  mock.list.mockResolvedValue({ data: [] });
  const user = userEvent.setup();
  view('/dashboard/standups?new=true');
  await screen.findByRole('dialog');
  await chooseOption(user, 'Channel', '#design');
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  await waitFor(() => expect(mock.create).toHaveBeenCalled());
  for (const field of Object.keys(workspaceSettings)) {
    expect(mock.create.mock.calls[0][0]).not.toHaveProperty(field);
  }
});

it('saves deliberate shared-setting changes while creating a standup, including cleared values', async () => {
  mock.list.mockResolvedValue({ data: [{ ...standup, ...workspaceSettings }] });
  const user = userEvent.setup();
  view('/dashboard/standups?new=true');
  await screen.findByRole('dialog');
  await chooseOption(user, 'Channel', '#design');
  await user.click(screen.getByRole('tab', { name: 'Advanced' }));
  await chooseOption(user, 'Edit window', 'Until report time');
  await chooseOption(user, 'AI provider', 'OpenAI');
  await user.click(screen.getByLabelText('Enable AI-generated daily summary'));
  await user.clear(screen.getByLabelText('Jira base URL'));
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  await waitFor(() =>
    expect(mock.create).toHaveBeenCalledWith(
      expect.objectContaining({
        edit_window: 'report',
        ai_provider: 'openai',
        ai_summary_enabled: false,
        jira_base_url: '',
      }),
    ),
  );
  expect(mock.create.mock.calls[0][0]).not.toHaveProperty('github_repo');
  expect(mock.create.mock.calls[0][0]).not.toHaveProperty('linear_team');
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

describe('standup loading transitions', () => {
  it.each(['content', 'empty', 'error'] as const)(
    'replaces its skeleton with %s',
    async (outcome) => {
      const response = deferred<{ data: Standup[] }>();
      mock.list.mockReturnValue(response.promise);
      view();
      expect(
        screen.getByRole('status', { name: 'Loading standups…' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: 'Standups' }),
      ).toBeInTheDocument();
      expect(
        screen.queryByText('Your first standup starts here'),
      ).not.toBeInTheDocument();
      await act(async () => {
        if (outcome === 'error') response.reject(new Error('Offline'));
        else response.resolve({ data: outcome === 'empty' ? [] : [standup] });
      });
      expect(
        await screen.findByText(
          outcome === 'error'
            ? 'Could not load this view'
            : outcome === 'empty'
              ? 'Your first standup starts here'
              : 'Design daily',
        ),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('status', { name: 'Loading standups…' }),
      ).not.toBeInTheDocument();
    },
  );

  it('keeps cached standups visible during a background refresh', async () => {
    const client = view();
    await screen.findByText('Design daily');
    const response = deferred<{ data: Standup[] }>();
    mock.list.mockReturnValue(response.promise);
    let refresh!: Promise<void>;
    act(() => {
      refresh = client.invalidateQueries({
        queryKey: ['workspace', 'T1', 'standups'],
      });
    });
    await waitFor(() => expect(mock.list).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Design daily')).toBeInTheDocument();
    expect(
      screen.queryByRole('status', { name: 'Loading standups…' }),
    ).not.toBeInTheDocument();
    await act(async () => {
      response.resolve({ data: [standup] });
      await refresh;
    });
  });
});
