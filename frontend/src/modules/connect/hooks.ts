import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

export type Program = Awaited<
  ReturnType<typeof api.connect.listPrograms>
>['data'][number];
export type ProgramInput = Parameters<typeof api.connect.createProgram>[0];
export type ProgramMemberInput = Parameters<
  typeof api.connect.updateProgramMember
>[1];

export function useConnect() {
  const { data: session } = useSession();

  return useQuery({
    queryKey: ['workspace', session?.team_id, 'connect', 'programs'],
    queryFn: ({ signal }) =>
      api.connect.listPrograms({ signal }).then((r) => r.data),
    enabled: !!session,
  });
}

export function useConnectCapabilities() {
  const { data: session } = useSession();

  const modules = useQuery({
    queryKey: ['workspace', session?.team_id, 'modules'],
    queryFn: ({ signal }) =>
      api.workspace.listModules({ signal }).then((r) => r.data),
    enabled: !!session,
  });

  return modules;
}

export function useConnectResources() {
  const { data: session } = useSession();

  const channels = useQuery({
    queryKey: ['workspace', session?.team_id, 'channels'],
    queryFn: ({ signal }) =>
      api.workspace.listChannels({ signal }).then((r) => r.data),
    enabled: !!session,
  });

  const zoom = useQuery({
    queryKey: ['workspace', session?.team_id, 'connect', 'zoom'],
    queryFn: ({ signal }) =>
      api.connect.getZoom({ signal }).then((r) => r.data),
    enabled: !!session,
  });

  return { channels, zoom };
}

export function useProgramMembers(id: number) {
  const { data: session } = useSession();

  return useQuery({
    queryKey: ['workspace', session?.team_id, 'connect', id, 'members'],
    queryFn: ({ signal }) =>
      api.connect
        .listProgramMembers({ programId: id }, { signal })
        .then((r) => r.data),
    enabled: !!session && !!id,
  });
}

export function useAttendance(id: number) {
  const { data: session } = useSession();

  const rounds = useQuery({
    queryKey: ['workspace', session?.team_id, 'connect', id, 'rounds'],
    queryFn: ({ signal }) =>
      api.connect.listRounds({ programId: id }, { signal }).then((r) => r.data),
    enabled: !!session && !!id,
  });

  const participation = useQuery({
    queryKey: ['workspace', session?.team_id, 'connect', id, 'participation'],
    queryFn: ({ signal }) =>
      api.connect
        .listParticipation({ programId: id, rounds: 6 }, { signal })
        .then((r) => r.data),
    enabled: !!session && !!id,
  });

  const members = useMemberDirectory({ enabled: !!id });

  return { rounds, participation, members };
}

export function useRoundMatches(roundId: number) {
  const { data: session } = useSession();

  return useQuery({
    queryKey: ['workspace', session?.team_id, 'connect', 'matches', roundId],
    queryFn: ({ signal }) =>
      api.connect.listMatches({ roundId }, { signal }).then((r) => r.data),
    enabled: !!session && !!roundId,
  });
}

export function useConnectMutations() {
  const client = useQueryClient();
  const { data: session } = useSession();

  const invalidate = async () => {
    await client.invalidateQueries({
      queryKey: ['workspace', session?.team_id, 'connect'],
    });
  };

  const save = useMutation({
    mutationFn: ({ id, body }: { id?: number; body: ProgramInput }) =>
      id
        ? api.connect.updateProgram({ programId: id }, body).then((r) => r.data)
        : api.connect.createProgram(body).then((r) => r.data),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.connect.deleteProgram({ programId: id }),
    onSuccess: invalidate,
  });

  const run = useMutation({
    mutationFn: (id: number) => api.connect.runProgram({ programId: id }),
    onSuccess: invalidate,
  });

  const member = useMutation({
    mutationFn: ({
      id,
      userId,
      body,
    }: {
      id: number;
      userId: string;
      body: ProgramMemberInput;
    }) => api.connect.updateProgramMember({ programId: id, userId }, body),
    onSuccess: invalidate,
  });

  const enable = useMutation({
    mutationFn: () =>
      api.workspace.updateModule({ name: 'connect' }, { enabled: true }),
    onSuccess: async () => {
      await Promise.all([
        invalidate(),
        client.invalidateQueries({
          queryKey: ['workspace', session?.team_id, 'modules'],
        }),
      ]);
    },
  });

  return { save, remove, run, member, enable };
}
