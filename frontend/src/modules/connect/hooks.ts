import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import { channelsOptions, modulesOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

import {
  connectMatchesOptions,
  connectMembersOptions,
  connectParticipationOptions,
  connectProgramsOptions,
  connectRoundsOptions,
  connectZoomOptions,
} from './queries';

export type Program = Awaited<
  ReturnType<Api['connect']['listPrograms']>
>['data'][number];
export type ProgramInput = Parameters<Api['connect']['createProgram']>[0];
export type ProgramMemberInput = Parameters<
  Api['connect']['updateProgramMember']
>[1];

export function useConnect() {
  const services = useServices();
  const { data: session } = useSession();

  return useQuery(connectProgramsOptions(services, session?.team_id));
}

export function useConnectCapabilities() {
  const services = useServices();
  const { data: session } = useSession();

  const modules = useQuery(modulesOptions(services, session?.team_id));

  return modules;
}

export function useConnectResources() {
  const services = useServices();
  const { data: session } = useSession();

  const channels = useQuery(channelsOptions(services, session?.team_id));
  const zoom = useQuery(connectZoomOptions(services, session?.team_id));

  return { channels, zoom };
}

export function useProgramMembers(id: number) {
  const services = useServices();
  const { data: session } = useSession();

  return useQuery(connectMembersOptions(services, session?.team_id, id));
}

export function useAttendance(id: number) {
  const services = useServices();
  const { data: session } = useSession();

  const rounds = useQuery(connectRoundsOptions(services, session?.team_id, id));
  const participation = useQuery(
    connectParticipationOptions(services, session?.team_id, id),
  );

  const members = useMemberDirectory({ enabled: !!id });

  return { rounds, participation, members };
}

export function useRoundMatches(roundId: number) {
  const services = useServices();
  const { data: session } = useSession();

  return useQuery(connectMatchesOptions(services, session?.team_id, roundId));
}

export function useConnectMutations() {
  const services = useServices();
  const { api } = services;
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

      services.invalidateRouter();
    },
  });

  return { save, remove, run, member, enable };
}
