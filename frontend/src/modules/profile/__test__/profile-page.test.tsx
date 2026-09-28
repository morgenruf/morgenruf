import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TestRouter } from '@/test/router';
import { chooseOption } from '@/test/select';

import ProfilePage from '../pages/profile-page';

const mock = vi.hoisted(() => ({ get: vi.fn(), update: vi.fn() }));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({
    data: { team_id: 'T1', user_id: 'U1', role: 'member' },
  }),
}));

vi.mock('@/common/api/services-context', async (importOriginal) => {
  const actual = await importOriginal<object>();
  const api = {
    profile: { getMyProfile: mock.get, updateMyProfile: mock.update },
  };

  return {
    ...actual,
    useApi: () => api,
    useServices: () => ({ api, invalidateRouter: vi.fn() }),
  };
});

const empty = {
  user_id: 'U1',
  birth_month: null,
  birth_day: null,
  start_date: null,
  role: null,
  location: null,
  ask_me_about: null,
  celebrate: true,
  updated_by: null,
  updated_at: null,
  set_by_admin: false,
  left_at: null,
};

function view() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <TestRouter routeId="/dashboard/_authenticated/profile">
        <ProfilePage />
      </TestRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mock.get.mockResolvedValue({ data: empty });
  mock.update.mockImplementation((data) =>
    Promise.resolve({ data: { ...empty, ...data, updated_by: 'U1' } }),
  );
});

describe('my profile', () => {
  it('saves a 29 February birthday and the rest of the profile', async () => {
    const user = userEvent.setup({ delay: null });

    view();
    await screen.findByRole('combobox', { name: 'Birthday month' });

    await chooseOption(user, 'Birthday month', 'February');
    await chooseOption(user, 'Birthday day', '29');
    await user.type(screen.getByLabelText('Role'), 'Designer');
    await user.type(screen.getByLabelText('Location'), 'Lisbon');
    await user.click(screen.getByLabelText('Don’t celebrate me publicly'));
    await user.click(screen.getByRole('button', { name: 'Save profile' }));

    await waitFor(() =>
      expect(mock.update).toHaveBeenCalledWith({
        birth_month: 2,
        birth_day: 29,
        start_date: null,
        role: 'Designer',
        location: 'Lisbon',
        ask_me_about: null,
        celebrate: false,
      }),
    );
  });

  it('refuses a day the month does not have before sending anything', async () => {
    const user = userEvent.setup({ delay: null });

    view();
    await screen.findByRole('combobox', { name: 'Birthday month' });

    await chooseOption(user, 'Birthday month', 'April');
    await chooseOption(user, 'Birthday day', '31');
    await user.click(screen.getByRole('button', { name: 'Save profile' }));

    expect(
      await screen.findByText('That day does not exist in that month.'),
    ).toBeInTheDocument();
    expect(mock.update).not.toHaveBeenCalled();
  });

  it('shows the server’s field errors on the field', async () => {
    mock.update.mockRejectedValue({
      error: {
        error: 'Invalid',
        details: { location: ['Longer than maximum length 80.'] },
      },
    });
    const user = userEvent.setup({ delay: null });

    view();
    await user.type(await screen.findByLabelText('Location'), 'Somewhere');
    await user.click(screen.getByRole('button', { name: 'Save profile' }));

    expect(
      await screen.findByText('Longer than maximum length 80.'),
    ).toBeInTheDocument();
  });

  it('says when an admin filled it in', async () => {
    mock.get.mockResolvedValue({
      data: {
        ...empty,
        birth_month: 3,
        birth_day: 14,
        updated_by: 'U_ADMIN',
        set_by_admin: true,
      },
    });

    view();

    expect(
      await screen.findByText(/An admin filled in some of this/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: 'Birthday month' }),
    ).toHaveTextContent('March');
  });
});
