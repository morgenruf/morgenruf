import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMemberDirectory } from '../use-member-directory';

const mock = vi.hoisted(() => ({ team: 'T1', listMembers: vi.fn() }));

vi.mock('@/common/auth/use-session', () => ({
  useSession: () => ({ data: { team_id: mock.team } }),
}));
vi.mock('@/common/api/client', () => ({
  api: { members: { listMembers: mock.listMembers } },
}));

function Identity({
  id = 'U1',
  fallback = 'Saved name',
  channel,
}: {
  id?: string;
  fallback?: string;
  channel?: string;
}) {
  const directory = useMemberDirectory({ channel });
  const person = directory.person(id, fallback);
  return <span data-avatar={person.avatar}>{person.name}</span>;
}

function client() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
}

beforeEach(() => {
  mock.team = 'T1';
  mock.listMembers.mockReset();
});

describe('shared member directory', () => {
  it('shares one workspace request across consumers and follows name precedence', async () => {
    mock.listMembers.mockResolvedValue({
      data: [
        {
          id: 'U1',
          name: ' Ada Lovelace ',
          display_name: 'ada',
          avatar: '/ada.png',
        },
        { id: 'U2', name: ' ', display_name: 'sam', avatar: '' },
      ],
    });
    const cache = client();
    render(
      <QueryClientProvider client={cache}>
        <Identity />
        <Identity />
        <Identity id="U2" />
        <Identity id="unknown" fallback="" />
      </QueryClientProvider>,
    );
    expect(await screen.findAllByText('Ada Lovelace')).toHaveLength(2);
    expect(screen.getByText('sam')).toBeInTheDocument();
    expect(screen.getByText('unknown')).toBeInTheDocument();
    expect(screen.getAllByText('Ada Lovelace')[0]).toHaveAttribute(
      'data-avatar',
      '/ada.png',
    );
    expect(mock.listMembers).toHaveBeenCalledTimes(1);
    expect(mock.listMembers).toHaveBeenCalledWith(
      {},
      { signal: expect.any(AbortSignal) },
    );
    expect(cache.getQueryData(['workspace', 'T1', 'members', ''])).toHaveLength(
      2,
    );
  });

  it('keeps response names visible while loading and after a directory failure', async () => {
    let reject!: (error: Error) => void;
    mock.listMembers.mockReturnValue(
      new Promise((_resolve, rejectRequest) => {
        reject = rejectRequest;
      }),
    );
    const cache = client();
    render(
      <QueryClientProvider client={cache}>
        <Identity />
      </QueryClientProvider>,
    );
    expect(screen.getByText('Saved name')).toBeInTheDocument();
    reject(new Error('Directory unavailable'));
    await waitFor(() =>
      expect(
        cache.getQueryState(['workspace', 'T1', 'members', ''])?.status,
      ).toBe('error'),
    );
    expect(screen.getByText('Saved name')).toBeInTheDocument();
  });

  it('separates channel and workspace caches', async () => {
    mock.listMembers.mockResolvedValue({
      data: [{ id: 'U1', name: 'Team one', avatar: '' }],
    });
    const cache = client();
    const { rerender } = render(
      <QueryClientProvider client={cache}>
        <Identity channel="C1" />
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Team one')).toBeInTheDocument();
    expect(mock.listMembers).toHaveBeenCalledWith(
      { channel_id: 'C1' },
      { signal: expect.any(AbortSignal) },
    );

    mock.team = 'T2';
    mock.listMembers.mockResolvedValue({
      data: [{ id: 'U1', name: 'Team two', avatar: '' }],
    });
    rerender(
      <QueryClientProvider client={cache}>
        <Identity channel="C1" />
      </QueryClientProvider>,
    );
    expect(screen.queryByText('Team one')).not.toBeInTheDocument();
    expect(await screen.findByText('Team two')).toBeInTheDocument();
    expect(mock.listMembers).toHaveBeenCalledTimes(2);
  });
});
