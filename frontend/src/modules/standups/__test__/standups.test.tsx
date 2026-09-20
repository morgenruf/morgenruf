import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Standup } from '@/common/api/generated/data-contracts';
import { deferred } from '@/test/deferred';
import { chooseOption } from '@/test/select';

import { StandupsPage } from '../pages';

const mock = vi.hoisted(() => ({
  editable: true,
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
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
      deleteStandup: mock.remove,
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

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function view(path = '/dashboard/standups') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <StandupsPage />
        <Location />
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
  mock.remove.mockResolvedValue({ data: {} });
});

describe('standup management', () => {
  it('keeps participant names accessible and selectable beside their avatars', async () => {
    mock.members.mockResolvedValue({
      data: [
        {
          id: 'U1',
          display_name: 'Mina',
          avatar: 'https://example.com/mina.png',
        },
      ],
    });
    const user = userEvent.setup();
    view('/dashboard/standups?edit=7');
    const participant = await screen.findByRole('checkbox', { name: 'Mina' });
    expect(participant.closest('label')?.querySelector('img')).toHaveAttribute(
      'src',
      'https://example.com/mina.png',
    );
    await user.click(screen.getByText('Mina'));
    expect(participant).toBeChecked();
    participant.focus();
    await user.keyboard(' ');
    expect(participant).not.toBeChecked();
    await user.keyboard(' ');
    expect(participant).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Save standup' }));
    await waitFor(() =>
      expect(mock.update).toHaveBeenCalledWith(
        { standupId: 7 },
        expect.objectContaining({ participants: ['U1'] }),
      ),
    );
  });

  it('searches participant identities and adds results without losing hidden selections', async () => {
    mock.members.mockResolvedValue({
      data: [
        {
          id: 'U1',
          name: 'Mina',
          display_name: 'mina.design',
          email: 'mina@example.com',
        },
        {
          id: 'U2',
          name: 'Arun',
          display_name: 'arun.engineering',
          email: 'arun@example.com',
        },
        {
          id: 'U3',
          name: 'Sam',
          display_name: 'sam.engineering',
          email: 'sam@example.com',
        },
      ],
    });
    const user = userEvent.setup();
    view('/dashboard/standups?edit=7');
    await user.click(await screen.findByRole('checkbox', { name: 'Mina' }));
    const search = screen.getByRole('textbox', { name: 'Search participants' });
    await user.type(search, '  ENGINEERING  ');
    expect(
      screen.queryByRole('checkbox', { name: 'Mina' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Select results' }));
    await user.click(screen.getByRole('button', { name: 'Select results' }));
    expect(screen.getByText('3 selected')).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: 'Clear participant search' }),
    );
    expect(search).toHaveFocus();
    expect(screen.getByRole('checkbox', { name: 'Mina' })).toBeChecked();
    for (const query of ['mINa', 'MINA@EXAMPLE.COM', 'u1']) {
      await user.clear(search);
      await user.type(search, query);
      expect(screen.getByRole('checkbox', { name: 'Mina' })).toBeChecked();
      expect(
        screen.queryByRole('checkbox', { name: 'Arun' }),
      ).not.toBeInTheDocument();
    }
    await user.clear(search);
    await user.type(search, 'nobody-matches');
    expect(
      screen.getByText('No participants match your search.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Select results' }),
    ).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Save standup' }));
    await waitFor(() =>
      expect(mock.update).toHaveBeenCalledWith(
        { standupId: 7 },
        expect.objectContaining({ participants: ['U1', 'U2', 'U3'] }),
      ),
    );
  });

  it('selects all participants and restores whole-channel enrollment', async () => {
    mock.members.mockResolvedValue({
      data: [
        { id: 'U1', name: 'Mina' },
        { id: 'U2', name: 'Arun' },
      ],
    });
    const user = userEvent.setup();
    view('/dashboard/standups?edit=7');
    await screen.findByRole('checkbox', { name: 'Mina' });
    await user.click(
      screen.getByRole('button', { name: 'Select all participants' }),
    );
    expect(screen.getByText('2 selected')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Arun' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Use whole channel' }));
    expect(screen.getByRole('checkbox', { name: 'Mina' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Arun' })).not.toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Save standup' }));
    await waitFor(() =>
      expect(mock.update).toHaveBeenCalledWith(
        { standupId: 7 },
        expect.objectContaining({ participants: [] }),
      ),
    );
  });

  it('explains empty participant and template lists', async () => {
    mock.members.mockResolvedValue({ data: [] });
    mock.templates.mockResolvedValue({ data: [] });
    const user = userEvent.setup();
    view('/dashboard/standups?edit=7');
    expect(
      await screen.findByText('No participants available.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Select all participants' }),
    ).toBeDisabled();
    await user.click(screen.getByRole('tab', { name: 'Questions' }));
    await user.click(screen.getByRole('button', { name: 'Use a template' }));
    expect(
      await screen.findByText('No question templates available.'),
    ).toBeInTheDocument();
  });

  it('shows whole-channel enrollment and hides mutations for read-only members', async () => {
    mock.editable = false;

    view();

    expect(await screen.findByText('Design daily')).toBeInTheDocument();
    expect(screen.getByText('Everyone in the channel')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^Edit/ }),
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

    await user.click(screen.getByRole('tab', { name: 'Questions' }));
    await user.click(screen.getByRole('button', { name: 'Use a template' }));
    await user.click(
      await screen.findByRole('button', { name: /Retrospective/ }),
    );

    expect(screen.getByLabelText('Question 1')).toHaveValue('What worked?');

    await user.click(screen.getByRole('tab', { name: 'Delivery' }));
    await user.type(
      screen.getByLabelText(/Daily email to/),
      'lead@example.com',
    );
    await user.click(
      screen.getByRole('checkbox', { name: 'Send that email daily' }),
    );

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
  ['Delivery', 'Daily email to', 'bad-address', 'lead@example.com'],
  ['Workspace', 'Jira base URL', 'bad-url', 'https://team.atlassian.net'],
  [
    'Delivery',
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
  await user.click(screen.getByRole('tab', { name: 'Workspace' }));
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
    screen.getByRole('checkbox', { name: 'Enable AI-generated daily summary' }),
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
  await user.click(screen.getByRole('tab', { name: 'Workspace' }));
  await chooseOption(user, 'Edit window', 'Until report time');
  await chooseOption(user, 'AI provider', 'OpenAI');
  await user.click(
    screen.getByRole('checkbox', { name: 'Enable AI-generated daily summary' }),
  );
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
    await user.click(screen.getByRole('tab', { name: 'Delivery' }));
    expect(
      screen.getByRole('combobox', { name: 'Report channel' }),
    ).toHaveTextContent('#design');
    await chooseOption(user, 'Report channel', 'Same as standup channel');
    await chooseOption(user, 'Group report by', 'Question');
    await user.click(screen.getByRole('tab', { name: 'Workspace' }));
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

describe('standup overview', () => {
  const second = {
    ...standup,
    id: 8,
    name: 'Platform sync',
    channel_id: 'C2',
    schedule_time: '08:00',
    active: false,
  };

  it('combines name/channel search with status, keeps chronological order, and preserves filters around dialogs', async () => {
    mock.list.mockResolvedValue({ data: [standup, second] });
    mock.channels.mockResolvedValue({
      data: [
        { id: 'C1', name: 'design' },
        { id: 'C2', name: 'platform' },
      ],
    });
    const user = userEvent.setup();
    view();
    const list = await screen.findByRole('list', { name: 'Standup schedules' });
    expect(
      within(list)
        .getAllByRole('heading')
        .map((node) => node.textContent),
    ).toEqual(['Platform sync', 'Design daily']);
    await user.type(
      screen.getByRole('textbox', { name: 'Search standups' }),
      '#PLATFORM',
    );
    await user.click(screen.getByRole('tab', { name: 'Paused 1' }));
    expect(within(list).getAllByRole('heading')).toHaveLength(1);
    await user.click(
      screen.getByRole('button', { name: 'Edit Platform sync' }),
    );
    expect(screen.getByTestId('location')).toHaveTextContent(
      'q=%23PLATFORM&status=paused&edit=8',
    );
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByTestId('location')).toHaveTextContent(
      '?q=%23PLATFORM&status=paused',
    );
    expect(screen.getByTestId('location')).not.toHaveTextContent('edit=');
    await user.click(screen.getByRole('button', { name: 'New standup' }));
    expect(screen.getByTestId('location')).toHaveTextContent(
      'status=paused&new=true',
    );
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('tab', { name: 'Active 1' }));
    expect(screen.getByText('No matching standups')).toBeInTheDocument();
    expect(
      screen.queryByText('Your first standup starts here'),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(screen.getByTestId('location')).toBeEmptyDOMElement();
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(2);
  });

  it.each([
    [85, 20, 'Healthy', '85%'],
    [50, 20, 'Slipping', '50%'],
    [0, 20, 'Needs a look', '0%'],
    [0, 0, 'No participation data', null],
    [null, 20, 'No participation data', null],
  ])(
    'renders rate %s with %s expected responses honestly',
    async (rate, expected, label, percent) => {
      mock.analytics.mockResolvedValue({
        data: {
          schedules: [
            {
              schedule_id: 7,
              completed: 0,
              expected,
              completion_rate: rate,
              series: [null, 20, 40, null, 60, 80],
            },
          ],
        },
      });
      view();
      const list = await screen.findByRole('list', {
        name: 'Standup schedules',
      });
      expect(await within(list).findByText(label)).toBeInTheDocument();
      if (percent) {
        expect(within(list).getByText(percent)).toBeInTheDocument();
        expect(
          within(list).queryByText('No participation data'),
        ).not.toBeInTheDocument();
      } else {
        expect(within(list).queryByText('0%')).not.toBeInTheDocument();
        expect(
          within(list).getByText('Stats appear after scheduled check-ins.'),
        ).toBeInTheDocument();
      }
    },
  );

  it('keeps schedules available when participation fails and supports retry', async () => {
    mock.analytics.mockRejectedValueOnce(new Error('Analytics unavailable'));
    const user = userEvent.setup();
    view();
    await screen.findByRole('button', { name: 'Retry participation' });
    expect(
      screen.getByRole('heading', { name: 'Design daily' }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: 'Retry participation' }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Retry participation' }),
      ).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByText('No participation data'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Stats appear after scheduled check-ins.'),
    ).toBeInTheDocument();
  });

  it('shows registration errors and omits next run for paused schedules', async () => {
    mock.list.mockResolvedValue({
      data: [
        {
          ...standup,
          registration_error: 'Timezone is unavailable',
          next_run: '2026-09-21T09:00:00Z',
        },
        { ...second, next_run: '2026-09-21T09:00:00Z' },
      ],
    });
    view();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This standup never runs. Timezone is unavailable',
    );
    expect(screen.getByText('Schedule paused')).toBeInTheDocument();
    expect(screen.queryByText(/^Next:/)).not.toBeInTheDocument();
  });

  it.each([true, false])(
    'changes active=%s from the menu and blocks duplicate actions',
    async (active) => {
      mock.list.mockResolvedValue({ data: [{ ...standup, active }] });
      const response = deferred<{ data: Standup }>();
      mock.update.mockReturnValue(response.promise);
      const user = userEvent.setup();
      view();
      await user.click(
        await screen.findByRole('button', { name: 'Actions for Design daily' }),
      );
      await user.click(
        await screen.findByRole('menuitem', {
          name: active ? 'Pause' : 'Resume',
        }),
      );
      await waitFor(() =>
        expect(mock.update).toHaveBeenCalledWith(
          { standupId: 7 },
          { active: !active },
        ),
      );
      expect(
        screen.getByRole('button', { name: 'Actions for Design daily' }),
      ).toBeDisabled();
      expect(
        screen.getByRole('button', { name: 'Edit Design daily' }),
      ).toBeDisabled();
      await act(async () =>
        response.resolve({ data: { ...standup, active: !active } }),
      );
      await waitFor(() =>
        expect(
          screen.getByRole('button', { name: 'Actions for Design daily' }),
        ).toBeEnabled(),
      );
    },
  );

  it('requires delete confirmation, retains errors, and protects a pending deletion', async () => {
    const user = userEvent.setup();
    view();
    (
      await screen.findByRole('button', { name: 'Actions for Design daily' })
    ).focus();
    await user.keyboard('{Enter}');
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    expect(screen.getByRole('alertdialog')).toHaveAccessibleName(
      'Delete Design daily?',
    );
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mock.remove).not.toHaveBeenCalled();
    screen.getByRole('button', { name: 'Actions for Design daily' }).focus();
    await user.keyboard('{Enter}');
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    mock.remove.mockRejectedValueOnce(
      new Error('Could not delete this standup'),
    );
    await user.click(screen.getByRole('button', { name: 'Delete standup' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not delete this standup',
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    const response = deferred<{ data: object }>();
    mock.remove.mockReturnValueOnce(response.promise);
    await user.click(screen.getByRole('button', { name: 'Delete standup' }));
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Deleting…' })).toBeDisabled();
    await user.keyboard('{Escape}');
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    mock.list.mockResolvedValue({ data: [] });
    await act(async () => response.resolve({ data: {} }));
    expect(
      await screen.findByText('Your first standup starts here'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});

it('opens and focuses the tab for a server field error', async () => {
  mock.update.mockRejectedValue({
    error: { details: { report_time: ['Choose a later report time.'] } },
  });
  const user = userEvent.setup();
  view('/dashboard/standups?edit=7');
  await screen.findByRole('dialog');
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  expect(
    await screen.findByText('Choose a later report time.'),
  ).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Delivery' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  expect(screen.getByLabelText('Report time')).toHaveFocus();
  expect(screen.getByLabelText('Report time')).toHaveAccessibleDescription(
    'Choose a later report time.',
  );
});

it('focuses empty questions and keeps edits while navigating tabs with the keyboard', async () => {
  const user = userEvent.setup();
  view('/dashboard/standups?edit=7');
  await screen.findByRole('dialog');
  await user.click(screen.getByRole('tab', { name: 'Questions' }));
  await user.clear(screen.getByLabelText('Question 1'));
  await user.click(screen.getByRole('tab', { name: 'Basics' }));
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  expect(screen.getByRole('tab', { name: 'Questions' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  expect(screen.getByLabelText('Question 1')).toHaveFocus();
  expect(screen.getByText('Add at least one question.')).toBeVisible();
  await user.type(screen.getByLabelText('Question 1'), 'What changed?');
  await user.click(screen.getByRole('tab', { name: 'Questions' }));
  await user.keyboard('{End}');
  expect(screen.getByRole('tab', { name: 'Workspace' })).toHaveFocus();
  await user.keyboard('{ArrowRight}');
  expect(screen.getByRole('tab', { name: 'Basics' })).toHaveFocus();
  await user.click(screen.getByRole('tab', { name: 'Questions' }));
  expect(screen.getByLabelText('Question 1')).toHaveValue('What changed?');
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  await waitFor(() => expect(mock.update).toHaveBeenCalledOnce());
});

it('recovers from empty weekday and question selections without losing the form', async () => {
  const user = userEvent.setup();
  view('/dashboard/standups?edit=7');
  await screen.findByRole('dialog');
  await user.click(screen.getByRole('tab', { name: 'Schedule' }));
  await user.click(screen.getByRole('button', { name: 'Mon' }));
  await user.click(screen.getByRole('button', { name: 'Wed' }));
  await user.click(screen.getByRole('tab', { name: 'Basics' }));
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  expect(screen.getByRole('button', { name: 'Mon' })).toHaveFocus();
  expect(screen.getByText('Choose at least one day.')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Tue' }));
  await user.click(screen.getByRole('tab', { name: 'Questions' }));
  await user.click(screen.getByRole('button', { name: 'Remove question 1' }));
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  expect(screen.getByRole('button', { name: 'Add question' })).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Use a template' }));
  await user.click(
    await screen.findByRole('button', { name: /Retrospective/ }),
  );
  await user.click(screen.getByRole('button', { name: 'Save standup' }));
  await waitFor(() =>
    expect(mock.update).toHaveBeenCalledWith(
      { standupId: 7 },
      expect.objectContaining({
        schedule_days: ['tue'],
        questions: ['What worked?'],
      }),
    ),
  );
});
