import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { chooseOption } from '@/test/select';

import { Attendance } from './attendance';
import { attendanceRate, programDefaults } from './form-utils';
import type { Program } from './hooks';
import { ConnectListPage, ConnectNewPage } from './pages';
import { ProgramForm } from './program-form';

const mock = vi.hoisted(() => ({
  admin: false,
  modules: vi.fn(),
  programs: vi.fn(),
  rounds: vi.fn(),
  participation: vi.fn(),
  matches: vi.fn(),
  create: vi.fn(),
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

vi.mock('@/common/api/client', () => ({
  api: {
    connect: {
      listPrograms: mock.programs,
      listRounds: mock.rounds,
      listParticipation: mock.participation,
      listMatches: mock.matches,
      getZoom: vi.fn(),
      createProgram: mock.create,
      listProgramMembers: mock.programMembers,
      updateProgram: vi.fn(),
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
      listMembers: vi.fn().mockResolvedValue({
        data: [
          { id: 'U1', name: 'Mina' },
          { id: 'U2', name: 'Sam' },
        ],
      }),
    },
  },
}));

function view(component = <ConnectListPage />) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{component}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();

  mock.admin = false;
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
    const user = userEvent.setup();

    view(<Attendance programId={2} />);

    expect(await screen.findByText('No outcomes yet')).toBeInTheDocument();
    expect(screen.getByText('Unknown, rather than a miss')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { expanded: false }));

    expect(await screen.findByText('Mina · Sam')).toBeInTheDocument();
    expect(mock.matches).toHaveBeenCalledWith(
      { roundId: 3 },
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
  const user = userEvent.setup();
  view(<ProgramForm />);
  await user.click(screen.getByRole('button', { name: 'Create coffee chat' }));
  expect(await screen.findByText('Choose a channel.')).toBeInTheDocument();
  const channel = screen.getByRole('combobox', { name: 'Draw people from' });
  expect(channel).toHaveAccessibleDescription(
    'Everyone eligible in this channel can be paired. People can opt out from Slack.',
  );
  await waitFor(() => expect(channel).toHaveFocus());
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
  await user.click(screen.getByRole('button', { name: 'Create coffee chat' }));
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
  const user = userEvent.setup();
  view(<ProgramForm />);
  const channel = screen.getByRole('combobox', { name: 'Draw people from' });
  expect(channel).toBeDisabled();
  await user.click(channel);
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Repeat every' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'On' })).toBeDisabled();
});

it('keeps the selected values and disables choices while saving a coffee chat', async () => {
  mock.admin = true;
  let resolveSave!: (value: { data: { id: number } }) => void;
  mock.create.mockReturnValue(
    new Promise((resolve) => {
      resolveSave = resolve;
    }),
  );
  const user = userEvent.setup();
  view(<ProgramForm />);
  await chooseOption(user, 'Draw people from', '#engineering');
  await user.click(screen.getByRole('button', { name: 'Create coffee chat' }));
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

it('changes member participation through the status popup and blocks edits while pending', async () => {
  mock.admin = true;
  let resolveUpdate!: (value: { data: { state: string } }) => void;
  mock.updateMember.mockReturnValue(
    new Promise((resolve) => {
      resolveUpdate = resolve;
    }),
  );
  const user = userEvent.setup();
  const program = {
    ...programDefaults(),
    id: 2,
    channel_id: 'C1',
    created_at: null,
    team_id: 'T1',
  } as Program;
  view(<ProgramForm program={program} />);
  await user.click(screen.getByRole('tab', { name: 'Members' }));
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
