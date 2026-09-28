import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { AskForDatesDialog } from '@/common/components/ask-for-dates-dialog';
import { TestRouter } from '@/test/router';
import { chooseOption } from '@/test/select';

import CelebrationsPage from '../pages/celebrations-page';

const mock = vi.hoisted(() => ({
  admin: true,
  grant: true,
  active: true,
  settings: vi.fn(),
  save: vi.fn(),
  holidays: vi.fn(),
  addHoliday: vi.fn(),
  deleteHoliday: vi.fn(),
  importHolidays: vi.fn(),
  upcoming: vi.fn(),
  preview: vi.fn(),
  ask: vi.fn(),
  modules: vi.fn(),
  updateModule: vi.fn(),
  members: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: {
      team_id: 'T1',
      role: mock.admin ? 'admin' : 'member',
      module_admin: mock.grant ? ['celebrations'] : [],
    },
  }),
  usePermissions: () => ({
    isAdmin: mock.admin,
    canAdminister: (module: string) =>
      mock.admin || (mock.grant && module === 'celebrations'),
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    celebrations: {
      getCelebrationSettings: mock.settings,
      updateCelebrationSettings: mock.save,
      listHolidays: mock.holidays,
      addHoliday: mock.addHoliday,
      deleteHoliday: mock.deleteHoliday,
      importHolidays: mock.importHolidays,
      listUpcomingCelebrations: mock.upcoming,
      previewAskForDates: mock.preview,
      askForDates: mock.ask,
    },
    workspace: {
      listModules: mock.modules,
      listChannels: vi.fn().mockResolvedValue({
        data: [
          { id: 'C1', name: 'celebrations' },
          { id: 'C2', name: 'general' },
        ],
      }),
      updateModule: mock.updateModule,
    },
    members: { listMembers: mock.members },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

const settings = {
  channel_id: 'C1',
  timezone: 'Europe/Berlin',
  post_time: '09:00',
  birthdays: true,
  anniversaries: true,
  working_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
  ready: true,
  can_react: true,
  updated_at: null,
};

function view(children = <CelebrationsPage />) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <TestRouter routeId="/dashboard/_authenticated/celebrations">
        {children}
      </TestRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();

  mock.admin = true;
  mock.grant = true;
  mock.active = true;

  mock.settings.mockResolvedValue({ data: settings });
  mock.save.mockImplementation((data) =>
    Promise.resolve({ data: { ...settings, ...data } }),
  );
  mock.holidays.mockResolvedValue({
    data: [{ date: '2026-12-25', name: 'Christmas Day' }],
  });
  mock.addHoliday.mockResolvedValue({ data: [] });
  mock.deleteHoliday.mockResolvedValue({ data: [] });
  mock.upcoming.mockResolvedValue({
    data: [
      {
        kind: 'birthday',
        date: '2026-10-04',
        posted_on: '2026-10-02',
        user_id: 'U1',
        years: null,
      },
      {
        kind: 'anniversary',
        date: '2026-10-06',
        posted_on: '2026-10-06',
        user_id: 'U2',
        years: 3,
      },
    ],
  });
  mock.modules.mockImplementation(() =>
    Promise.resolve({
      data: [
        {
          name: 'celebrations',
          active: mock.active,
          enabled: mock.active,
          available: true,
          delegable: true,
          required_scopes: [],
          missing_scopes: [],
          nav: [],
        },
      ],
    }),
  );
  mock.members.mockResolvedValue({
    data: [
      { id: 'U1', name: 'Priya Shah' },
      { id: 'U2', name: 'Tom Berg' },
    ],
  });
  mock.preview.mockResolvedValue({
    data: {
      count: 12,
      ready: true,
      message:
        '👋 Hi Priya! Your team celebrates birthdays and work anniversaries in <#C1>.\n\nAdd yours so nobody misses it. Only day and month are kept.',
    },
  });
  mock.ask.mockResolvedValue({ data: { count: 12 } });
});

it('saves a Sunday to Thursday week with its own timezone and post time', async () => {
  const user = userEvent.setup({ delay: null });
  view();

  const sunday = await screen.findByRole('checkbox', { name: 'Sunday' });
  await user.click(sunday);
  await user.click(screen.getByRole('checkbox', { name: 'Friday' }));
  await chooseOption(user, 'Timezone', 'Asia/Dubai');
  const time = screen.getByLabelText('Post at');
  await user.clear(time);
  await user.type(time, '10:30');
  await user.click(
    screen.getByRole('checkbox', { name: 'Celebrate work anniversaries' }),
  );

  await user.click(screen.getByRole('button', { name: 'Save settings' }));

  await waitFor(() =>
    expect(mock.save).toHaveBeenCalledWith({
      channel_id: 'C1',
      timezone: 'Asia/Dubai',
      post_time: '10:30',
      birthdays: true,
      anniversaries: false,
      working_days: ['mon', 'tue', 'wed', 'thu', 'sun'],
    }),
  );
});

it('refuses a week with no working days before sending anything', async () => {
  const user = userEvent.setup({ delay: null });
  view();

  for (const day of ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])
    await user.click(await screen.findByRole('checkbox', { name: day }));

  await user.click(screen.getByRole('button', { name: 'Save settings' }));

  expect(
    await screen.findByText('Pick at least one working day.'),
  ).toBeInTheDocument();
  expect(mock.save).not.toHaveBeenCalled();
});

it('shows server field errors from the API', async () => {
  const user = userEvent.setup({ delay: null });
  mock.save.mockRejectedValue({
    error: {
      error: 'bad',
      details: { post_time: ['Use a 24-hour HH:MM time such as 09:30.'] },
    },
  });
  view();

  await user.click(
    await screen.findByRole('button', { name: 'Save settings' }),
  );

  expect(
    await screen.findByText('Use a 24-hour HH:MM time such as 09:30.'),
  ).toBeInTheDocument();
});

it('adds and removes holidays', async () => {
  const user = userEvent.setup({ delay: null });
  view();

  const list = await screen.findByRole('list', { name: 'Holidays' });
  expect(within(list).getByText('Christmas Day')).toBeInTheDocument();

  await user.type(screen.getByLabelText('Date'), '2027-01-01');
  await user.type(screen.getByLabelText('Name'), 'New Year');
  await user.click(screen.getByRole('button', { name: 'Add holiday' }));

  await waitFor(() =>
    expect(mock.addHoliday).toHaveBeenCalledWith({
      date: '2027-01-01',
      name: 'New Year',
    }),
  );

  await user.click(
    screen.getByRole('button', { name: 'Remove Christmas Day' }),
  );
  await waitFor(() =>
    expect(mock.deleteHoliday).toHaveBeenCalledWith({ day: '2026-12-25' }),
  );
});

it('previews a holiday import before saving it', async () => {
  const user = userEvent.setup({ delay: null });
  mock.importHolidays.mockImplementation(({ preview }) =>
    Promise.resolve({
      data: {
        preview,
        ready: 1,
        invalid: 1,
        written: preview ? 0 : 1,
        rows: [
          {
            line: 1,
            date: '2027-01-01',
            name: 'New Year',
            status: 'ready',
            error: null,
          },
          {
            line: 2,
            date: null,
            name: 'Oops',
            status: 'invalid',
            error: "Date 'soon' is not YYYY-MM-DD.",
          },
        ],
      },
    }),
  );
  view();

  await user.click(
    await screen.findByRole('button', { name: 'Import holidays' }),
  );
  await user.type(screen.getByLabelText('CSV'), '2027-01-01,New Year');
  await user.click(screen.getByRole('button', { name: 'Preview' }));

  const rows = await screen.findByRole('region', {
    name: 'Holidays in the file',
  });
  expect(within(rows).getByText('Will be saved')).toBeInTheDocument();
  expect(
    within(rows).getByText("Date 'soon' is not YYYY-MM-DD."),
  ).toBeVisible();
  expect(mock.importHolidays).toHaveBeenLastCalledWith({
    csv: '2027-01-01,New Year',
    preview: true,
  });

  await user.click(screen.getByRole('button', { name: 'Save 1 holiday' }));
  await waitFor(() =>
    expect(mock.importHolidays).toHaveBeenLastCalledWith({
      csv: '2027-01-01,New Year',
      preview: false,
    }),
  );
});

it('lists what is coming up and when an early post goes out', async () => {
  view();

  const list = await screen.findByRole('list', {
    name: 'Upcoming celebrations',
  });
  await waitFor(() =>
    expect(within(list).getByText('Priya Shah')).toBeInTheDocument(),
  );
  expect(within(list).getByText('🎂 Birthday')).toBeInTheDocument();
  expect(
    within(list).getByText('🎉 3-year work anniversary'),
  ).toBeInTheDocument();
  expect(within(list).getAllByText(/^posted/)).toHaveLength(1);
});

it('lets a workspace admin turn it on once a channel and timezone are set', async () => {
  const user = userEvent.setup({ delay: null });
  mock.active = false;
  mock.updateModule.mockResolvedValue({
    data: { module: 'celebrations', enabled: true },
  });
  view();

  await user.click(
    await screen.findByRole('button', { name: 'Turn on celebrations' }),
  );
  await waitFor(() =>
    expect(mock.updateModule).toHaveBeenCalledWith(
      { name: 'celebrations' },
      { enabled: true },
    ),
  );
});

it('does not offer to turn it on before it can post', async () => {
  mock.active = false;
  mock.settings.mockResolvedValue({
    data: { ...settings, channel_id: null, timezone: null, ready: false },
  });
  view();

  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Turn on celebrations' }),
    ).toBeDisabled(),
  );
  expect(
    screen.getByText('Choose a channel and a timezone below first.'),
  ).toBeInTheDocument();
});

it('lets a Celebrations admin set it up but not switch it on', async () => {
  mock.admin = false;
  mock.active = false;
  view();

  expect(
    await screen.findByText(
      'Set everything up below, then ask a workspace admin to turn Celebrations on.',
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Turn on celebrations' }),
  ).not.toBeInTheDocument();
  expect(
    await screen.findByRole('button', { name: 'Save settings' }),
  ).toBeInTheDocument();
});

it('is read only for a member without the grant', async () => {
  mock.admin = false;
  mock.grant = false;
  view();

  await screen.findByRole('list', { name: 'Holidays' });
  expect(
    screen.queryByRole('button', { name: 'Save settings' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Add holiday' }),
  ).not.toBeInTheDocument();
  expect(mock.upcoming).not.toHaveBeenCalled();
});

it('notes that the reaction needs a reinstall', async () => {
  mock.settings.mockResolvedValue({ data: { ...settings, can_react: false } });
  view();

  expect(
    await screen.findByText(/Posts go out without the 🎉 reaction/),
  ).toBeInTheDocument();
});

it('previews who will be asked for dates, then asks them', async () => {
  const user = userEvent.setup({ delay: null });
  const onOpenChange = vi.fn();
  view(<AskForDatesDialog open onOpenChange={onOpenChange} />);

  expect(await screen.findByText('12 people will be asked.')).toBeVisible();
  await waitFor(() =>
    expect(
      screen.getByText(/work anniversaries in #celebrations\./),
    ).toBeInTheDocument(),
  );

  await user.click(screen.getByRole('button', { name: 'Ask 12 people' }));

  await waitFor(() => expect(mock.ask).toHaveBeenCalledTimes(1));
  expect(onOpenChange).toHaveBeenCalledWith(false);
});

it('does not ask when nobody is missing dates', async () => {
  mock.preview.mockResolvedValue({
    data: { count: 0, ready: true, message: '👋 Hi Priya!' },
  });
  view(<AskForDatesDialog open onOpenChange={vi.fn()} />);

  expect(
    await screen.findByText(
      'Everyone has been asked recently or already has dates on file.',
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Ask 0 people' })).toBeDisabled();
});
