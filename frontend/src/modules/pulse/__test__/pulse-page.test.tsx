import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PulseRound } from '@/common/api/generated/data-contracts';
import { TestRouter } from '@/test/router';

import PulsePage from '../pages/pulse-page';
import { trendData } from '../trend-utils';

const mock = vi.hoisted(() => ({
  role: 'admin',
  settings: vi.fn(),
  save: vi.fn(),
  trend: vi.fn(),
  modules: vi.fn(),
  updateModule: vi.fn(),
}));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: { team_id: 'T1', role: mock.role, module_admin: [] },
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    pulse: {
      getPulseSettings: mock.settings,
      updatePulseSettings: mock.save,
      getPulseTrend: mock.trend,
    },
    workspace: {
      listModules: mock.modules,
      updateModule: mock.updateModule,
      listChannels: vi
        .fn()
        .mockResolvedValue({ data: [{ id: 'C1', name: 'team' }] }),
    },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

const rounds: PulseRound[] = [
  {
    sent_on: '2026-09-11',
    respondents: 6,
    invited: 8,
    hidden: false,
    includes_enps: true,
    mood_avg: 3.5,
    mood_dist: [0, 1, 2, 2, 1],
    enps: 17,
  },
  {
    sent_on: '2026-09-18',
    respondents: 3,
    invited: 8,
    hidden: true,
    needed: 5,
  },
  {
    sent_on: '2026-09-25',
    respondents: 7,
    invited: 8,
    hidden: false,
    includes_enps: false,
    mood_avg: 4.1,
    mood_dist: [0, 0, 1, 4, 2],
    enps: null,
  },
];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <TestRouter routeId="/dashboard/_authenticated/pulse">
        <PulsePage />
      </TestRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.role = 'admin';
  mock.settings.mockResolvedValue({
    data: {
      enabled: true,
      day_of_week: 4,
      hour: 14,
      minute: 0,
      timezone: 'UTC',
      audience_channel_id: null,
      updated_at: null,
    },
  });
  mock.trend.mockResolvedValue({ data: rounds });
  mock.modules.mockResolvedValue({
    data: [{ name: 'pulse', active: true }],
  });
  mock.save.mockImplementation((data) => Promise.resolve({ data }));
});

describe('trend', () => {
  it('turns a hidden round into a gap, never a number', () => {
    const data = trendData(rounds);
    expect(data.map((point) => point.mood)).toEqual([3.5, null, 4.1]);
    expect(data[1]).toMatchObject({ hidden: true, enps: null, rate: 38 });
  });

  it('draws the line with a gap where fewer than 5 answered', async () => {
    const { container } = renderPage();

    await screen.findByRole('group', { name: /Team mood by week/ });
    await waitFor(() =>
      expect(
        container.querySelectorAll('.recharts-line-dots [data-chart-dot]')
          .length,
      ).toBeGreaterThanOrEqual(2),
    );
    const moodCurve = container.querySelector('.recharts-line-curve');
    expect(moodCurve?.getAttribute('d')?.match(/M/g)).toHaveLength(2);

    await userEvent.setup().click(screen.getByText('View chart data'));
    const table = screen.getByRole('table', {
      name: 'Pulse results by week, oldest first',
    });
    expect(within(table).getByText('Fewer than 5 answers')).toBeInTheDocument();
    expect(within(table).getByText('3.5')).toBeInTheDocument();
  });

  it('shows an open week as a gap that says why', async () => {
    mock.trend.mockResolvedValue({
      data: [
        ...rounds,
        {
          sent_on: '2026-10-02',
          respondents: 9,
          invited: 10,
          hidden: true,
          needed: 5,
          open: true,
        },
      ],
    });
    renderPage();

    await screen.findByRole('group', { name: /Team mood by week/ });
    await userEvent.setup().click(screen.getByText('View chart data'));
    expect(
      within(screen.getByRole('table')).getByText(
        'Still open. Results show when it closes',
      ),
    ).toBeInTheDocument();
  });

  it('explains an empty history', async () => {
    mock.trend.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByText('No check-ins yet')).toBeInTheDocument();
  });

  it('says so when no week has reached five', async () => {
    mock.trend.mockResolvedValue({ data: [rounds[1]] });
    renderPage();
    expect(
      await screen.findByText('No closed week has 5 answers yet'),
    ).toBeInTheDocument();
  });
});

describe('settings', () => {
  it('saves the schedule as hour and minute', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();

    const time = await screen.findByLabelText('Time');
    await user.clear(time);
    await user.type(time, '09:30');
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    await waitFor(() =>
      expect(mock.save).toHaveBeenCalledWith({
        enabled: true,
        day_of_week: 4,
        hour: 9,
        minute: 30,
        timezone: 'UTC',
        audience_channel_id: '',
      }),
    );
  });

  it('refuses to save without a time', async () => {
    const user = userEvent.setup({ delay: null });
    renderPage();

    await user.clear(await screen.findByLabelText('Time'));
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    expect(await screen.findByText('Choose a time.')).toBeInTheDocument();
    expect(mock.save).not.toHaveBeenCalled();
  });

  it('is read only for a member', async () => {
    mock.role = 'member';
    renderPage();

    await screen.findByLabelText('Time');
    expect(
      screen.queryByRole('button', { name: 'Save settings' }),
    ).not.toBeInTheDocument();
  });

  it('offers admins a way to turn the module on', async () => {
    mock.modules.mockResolvedValue({
      data: [{ name: 'pulse', active: false }],
    });
    const user = userEvent.setup({ delay: null });
    renderPage();

    await user.click(
      await screen.findByRole('button', { name: 'Turn on Pulse' }),
    );
    await waitFor(() =>
      expect(mock.updateModule).toHaveBeenCalledWith(
        { name: 'pulse' },
        { enabled: true },
      ),
    );
  });
});
