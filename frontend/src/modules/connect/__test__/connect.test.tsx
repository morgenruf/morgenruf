import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { formatDate } from '@/common/lib/format';
import { TestRouter } from '@/test/router';
import { chooseOption } from '@/test/select';

import { Attendance } from '../attendance';
import { attendanceRate, programDefaults } from '../form-utils';
import type { Program, ProgramInput } from '../hooks';
import { ConnectDetailPage, ConnectListPage, ConnectNewPage } from '../pages';
import { ProgramForm } from '../program-form';

const mock = vi.hoisted(() => ({
  admin: false,
  modules: vi.fn(),
  programs: vi.fn(),
  rounds: vi.fn(),
  participation: vi.fn(),
  matches: vi.fn(),
  members: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  programMembers: vi.fn(),
  updateMember: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: 'T1' } }),
  usePermissions: () => ({
    isAdmin: mock.admin,
    canAdminister: () => mock.admin,
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    connect: {
      listPrograms: mock.programs,
      listRounds: mock.rounds,
      listParticipation: mock.participation,
      listMatches: mock.matches,
      getZoom: vi.fn(),
      createProgram: mock.create,
      listProgramMembers: mock.programMembers,
      updateProgram: mock.update,
      deleteProgram: vi.fn(),
      runProgram: vi.fn(),
      updateProgramMember: mock.updateMember,
    },
    workspace: {
      listModules: mock.modules,
      listChannels: vi
        .fn()
        .mockResolvedValue({ data: [{ id: 'C1', name: 'engineering' }] }),
      updateModule: vi.fn(),
    },
    members: {
      listMembers: mock.members,
    },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

function view(component = <ConnectListPage />, path = '/') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <TestRouter
        routeId={
          path.match(/^\/dashboard\/connect\/\d+$/)
            ? '/dashboard/_authenticated/connect/$programId'
            : '/dashboard/_authenticated/connect'
        }
        initialEntries={[path === '/' ? '/dashboard/connect' : path]}
      >
        {component}
      </TestRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();

  mock.admin = false;
  mock.members.mockResolvedValue({
    data: [
      { id: 'U1', name: 'Mina', avatar: 'https://example.com/mina.jpg' },
      { id: 'U2', name: '', display_name: 'Sam' },
    ],
  });
  mock.create.mockResolvedValue({ data: { id: 9 } });
  mock.programMembers.mockResolvedValue({
    data: [
      {
        user_id: 'U1',
        name: 'Mina',
        avatar: '',
        paired: 2,
        state: 'in',
        eligible: true,
        until: null,
      },
    ],
  });
  mock.updateMember.mockResolvedValue({ data: { state: 'snoozed' } });

  mock.modules.mockResolvedValue({
    data: [
      { name: 'connect', available: true, active: false, missing_scopes: [] },
    ],
  });

  mock.rounds.mockResolvedValue({
    data: [
      {
        id: 3,
        scheduled_for: '2026-09-18T10:00:00Z',
        matches: 2,
        met: 0,
        missed: 0,
        no_reply: 2,
        undelivered: 0,
        agreed: 0,
        rematch_requests: 0,
      },
    ],
  });

  mock.participation.mockResolvedValue({ data: [] });

  mock.matches.mockResolvedValue({
    data: [
      {
        id: 4,
        members: ['U1', 'U2'],
        status: 'no_reply',
        agreed_at: null,
        has_zoom: false,
      },
    ],
  });
});

describe('coffee chats', () => {
  it('does not offer a forbidden enable action to regular members', async () => {
    view();

    expect(
      await screen.findByText('Coffee chats are switched off'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Turn on coffee chats' }),
    ).not.toBeInTheDocument();
    expect(mock.programs).not.toHaveBeenCalled();
  });

  it('explains missing Slack scopes before loading programs', async () => {
    mock.admin = true;
    mock.modules.mockResolvedValue({
      data: [
        {
          name: 'connect',
          available: true,
          active: true,
          missing_scopes: ['mpim:write'],
        },
      ],
    });

    view();

    expect(await screen.findByText(/Missing: mpim:write/)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Re-authorise Slack' }),
    ).toHaveAttribute('href', '/install');
    expect(mock.programs).not.toHaveBeenCalled();
  });

  it('treats unknown outcomes as unknown and expands pairings', async () => {
    const user = userEvent.setup({ delay: null });

    view(<Attendance programId={2} />);

    expect(await screen.findByText('No outcomes yet')).toBeInTheDocument();
    expect(screen.getByText('Unknown, rather than a miss')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { expanded: false }));

    expect(await screen.findByText('Mina')).toBeInTheDocument();
    expect(screen.getByText('Sam')).toBeInTheDocument();
    expect(
      screen
        .getByText('Mina')
        .closest('span.inline-flex')
        ?.querySelector('img'),
    ).toHaveAttribute('src', 'https://example.com/mina.jpg');
    expect(mock.matches).toHaveBeenCalledWith(
      { roundId: 3 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    await user.click(screen.getByRole('button', { expanded: true }));

    expect(screen.queryByText('Mina')).not.toBeInTheDocument();
  });

  it('keeps pairings and participation readable if the member directory fails', async () => {
    mock.members.mockRejectedValue(new Error('Directory unavailable'));
    mock.participation.mockResolvedValue({
      data: [
        {
          user_id: 'U2',
          paired: 2,
          met: 0,
          missed: 0,
          no_reply: 2,
          last_met: null,
        },
        {
          user_id: 'U1',
          paired: 2,
          met: 1,
          missed: 0,
          no_reply: 1,
          last_met: null,
        },
      ],
    });
    const user = userEvent.setup();

    view(<Attendance programId={2} />);

    expect(
      await screen.findByText(
        'Names are temporarily unavailable; Slack IDs are shown.',
      ),
    ).toBeInTheDocument();

    const rows = within(
      screen.getByRole('table', {
        name: 'Participation over the last 6 rounds',
      }),
    ).getAllByRole('row');
    expect(rows[1]).toHaveTextContent('U2');
    expect(rows[2]).toHaveTextContent('U1');

    await user.click(screen.getByRole('button', { expanded: false }));

    expect(await screen.findAllByText('U1')).toHaveLength(2);
    expect(screen.getAllByText('U2')).toHaveLength(2);
    expect(screen.getByText('No answered outcomes yet')).toBeInTheDocument();
    expect(mock.participation).toHaveBeenCalledWith(
      { programId: 2, rounds: 6 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('calculates meeting rate from answered pairings only', () => {
    expect(attendanceRate(0, 0)).toBeNull();
    expect(attendanceRate(3, 1)).toBe(75);
    expect(attendanceRate(0, 2)).toBe(0);
  });
});

it('associates exact field labels without incorporating select options into their names', async () => {
  mock.admin = true;
  mock.modules.mockResolvedValue({
    data: [
      { name: 'connect', available: true, active: true, missing_scopes: [] },
    ],
  });

  view(<ConnectNewPage />);

  expect(
    await screen.findByRole('combobox', {
      name: 'Draw people from',
    }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('combobox', { name: 'Repeat every' }),
  ).toBeInTheDocument();
});

it('requires a coffee chat channel and submits numeric choices across tabs', async () => {
  mock.admin = true;
  const user = userEvent.setup({ delay: null });

  view(<ProgramForm />);

  await user.click(
    await screen.findByRole('button', { name: 'Create coffee chat' }),
  );

  expect(await screen.findByText('Choose a channel.')).toBeInTheDocument();

  const channel = await screen.findByRole('combobox', {
    name: 'Draw people from',
  });
  expect(channel).toHaveAccessibleDescription(
    'Everyone eligible in this channel can be paired. People can opt out from Slack.',
  );
  await waitFor(() => expect(channel).toHaveFocus());

  // React Hook Form schedules a second focus pass after invalid submission.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(mock.create).not.toHaveBeenCalled();

  await chooseOption(user, 'Draw people from', '#engineering');
  await chooseOption(user, 'Repeat every', '3 weeks');
  await chooseOption(user, 'On', 'Friday');
  await chooseOption(user, 'On', 'Monday');

  await user.click(screen.getByRole('tab', { name: 'Matching' }));
  await chooseOption(user, 'People in each group', '4 people');

  await user.click(screen.getByRole('tab', { name: 'Message' }));
  await chooseOption(user, 'How your team works', 'Fully remote');

  await user.click(screen.getByRole('tab', { name: 'Meeting' }));
  await chooseOption(user, 'Meeting length', '45 minutes');
  await chooseOption(user, 'How they meet', 'They sort it out');

  expect(
    screen.queryByLabelText('Shared meeting link'),
  ).not.toBeInTheDocument();

  await user.click(
    await screen.findByRole('button', { name: 'Create coffee chat' }),
  );

  await waitFor(() =>
    expect(mock.create).toHaveBeenCalledWith(
      expect.objectContaining({
        channel_id: 'C1',
        interval_weeks: 3,
        day_of_week: 0,
        group_size: 4,
        intro_tone: 'remote',
        meeting_minutes: 45,
        video_mode: 'none',
      }),
    ),
  );
}, 15_000);

it('disables coffee chat choices for read-only members', async () => {
  const user = userEvent.setup({ delay: null });

  view(<ProgramForm />);
  const channel = await screen.findByRole('combobox', {
    name: 'Draw people from',
  });
  expect(channel).toBeDisabled();

  await user.click(channel);

  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Repeat every' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'On' })).toBeDisabled();
});

it('reveals an invalid meeting link on its tab and allows saving after correction', async () => {
  mock.admin = true;
  const user = userEvent.setup({ delay: null });

  view(<ProgramForm />);

  await chooseOption(user, 'Draw people from', '#engineering');
  await user.click(screen.getByRole('tab', { name: 'Meeting' }));

  const link = screen.getByLabelText('Shared meeting link');
  await user.type(link, 'bad-url');
  await user.click(screen.getByRole('tab', { name: 'Basics' }));
  await user.click(
    await screen.findByRole('button', { name: 'Create coffee chat' }),
  );

  await waitFor(() => expect(link).toBeVisible());
  expect(link).toHaveFocus();
  expect(screen.getByRole('alert')).toHaveTextContent(
    (link as HTMLInputElement).validationMessage,
  );
  expect(mock.create).not.toHaveBeenCalled();

  await user.clear(link);
  await user.type(link, 'https://example.com/meeting');
  await user.click(
    await screen.findByRole('button', { name: 'Create coffee chat' }),
  );

  await waitFor(() =>
    expect(mock.create).toHaveBeenCalledWith(
      expect.objectContaining({ meeting_link: 'https://example.com/meeting' }),
    ),
  );
});

it('keeps the selected values and disables choices while saving a coffee chat', async () => {
  mock.admin = true;
  let resolveSave!: (value: { data: { id: number } }) => void;
  mock.create.mockReturnValue(
    new Promise((resolve) => {
      resolveSave = resolve;
    }),
  );

  const user = userEvent.setup({ delay: null });

  view(<ProgramForm />);

  await chooseOption(user, 'Draw people from', '#engineering');
  await user.click(
    await screen.findByRole('button', { name: 'Create coffee chat' }),
  );

  await waitFor(() =>
    expect(
      screen.getByRole('combobox', { name: 'Draw people from' }),
    ).toBeDisabled(),
  );
  expect(
    screen.getByRole('combobox', { name: 'Draw people from' }),
  ).toHaveTextContent('#engineering');
  expect(mock.create).toHaveBeenCalledWith(
    expect.objectContaining({ channel_id: 'C1', day_of_week: 0 }),
  );

  await act(async () => resolveSave({ data: { id: 9 } }));
});

it.each([
  ['Pause', true],
  ['Resume', false],
] as const)(
  'preserves %s and unsaved edits when saving coffee chat settings',
  async (action, enabled) => {
    mock.admin = true;
    let program = {
      ...programDefaults(),
      id: 2,
      channel_id: 'C1',
      created_at: null,
      team_id: 'T1',
      enabled,
    } as Program;
    mock.modules.mockResolvedValue({
      data: [
        { name: 'connect', available: true, active: true, missing_scopes: [] },
      ],
    });
    mock.programs.mockImplementation(async () => ({ data: [{ ...program }] }));
    mock.update.mockImplementation(async (_params, body: ProgramInput) => {
      program = { ...program, ...body } as Program;

      return { data: { ...program } };
    });

    const user = userEvent.setup({ delay: null });
    view(<ConnectDetailPage />, '/dashboard/connect/2');

    const name = await screen.findByRole('textbox', { name: 'Name' });
    await user.clear(name);
    await user.type(name, 'Updated coffee chat');
    await user.click(screen.getByRole('button', { name: action }));
    await screen.findByRole('button', {
      name: enabled ? 'Resume' : 'Pause',
    });
    expect(name).toHaveValue('Updated coffee chat');

    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(mock.update).toHaveBeenCalledTimes(2));
    expect(program.name).toBe('Updated coffee chat');
    expect(program.enabled).toBe(!enabled);
    expect(mock.update.mock.calls[1][1]).not.toHaveProperty('enabled');
  },
);

it('changes member participation through the status popup and blocks edits while pending', async () => {
  mock.admin = true;
  let resolveUpdate!: (value: { data: { state: string } }) => void;
  mock.updateMember.mockReturnValue(
    new Promise((resolve) => {
      resolveUpdate = resolve;
    }),
  );

  const user = userEvent.setup({ delay: null });
  const program = {
    ...programDefaults(),
    id: 2,
    channel_id: 'C1',
    created_at: null,
    team_id: 'T1',
  } as Program;

  view(<ProgramForm program={program} />);
  await user.click(await screen.findByRole('tab', { name: 'Members' }));
  const status = await screen.findByRole('combobox', {
    name: 'Status for Mina',
  });
  expect(status).toHaveTextContent('In the pool');

  await chooseOption(user, 'Status for Mina', 'Snoozed 2 weeks');

  await waitFor(() =>
    expect(mock.updateMember).toHaveBeenCalledWith(
      { programId: 2, userId: 'U1' },
      { state: 'snoozed', weeks: 2 },
    ),
  );
  expect(status).toBeDisabled();

  mock.programMembers.mockResolvedValue({
    data: [
      {
        user_id: 'U1',
        name: 'Mina',
        avatar: '',
        paired: 2,
        state: 'snoozed',
        eligible: true,
        until: null,
      },
    ],
  });
  await act(async () => resolveUpdate({ data: { state: 'snoozed' } }));

  await waitFor(() => expect(status).toHaveTextContent('Snoozed 2 weeks'));
  expect(status).toBeEnabled();
});

it('shows the next round the scheduler will run, marking a pinned date', async () => {
  mock.admin = true;
  const shown = (iso: string) =>
    `Next round: ${formatDate(iso, { weekday: 'long', day: 'numeric', month: 'long' })}`;
  const program = {
    ...programDefaults(),
    id: 2,
    channel_id: 'C1',
    created_at: null,
    team_id: 'T1',
    enabled: true,
    upcoming_round: '2026-09-28',
    next_round_date: null,
  } as Program;
  mock.modules.mockResolvedValue({
    data: [
      { name: 'connect', available: true, active: true, missing_scopes: [] },
    ],
  });
  mock.programs.mockResolvedValue({ data: [program] });

  const { unmount } = view();

  expect(await screen.findByText(shown('2026-09-28'))).toBeInTheDocument();
  expect(screen.queryByText(/pinned date/)).not.toBeInTheDocument();

  unmount();
  mock.programs.mockResolvedValue({
    data: [
      {
        ...program,
        upcoming_round: '2026-10-12',
        next_round_date: '2026-10-07',
      },
    ],
  });
  view();

  expect(
    await screen.findByText(`${shown('2026-10-12')} (pinned date)`),
  ).toBeInTheDocument();
});
