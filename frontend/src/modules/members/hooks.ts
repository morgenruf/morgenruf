import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

export function useMembers(channel?: string, loadInviteRoster = false) {
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();

  const members = useMemberDirectory({ channel });
  const inviteMembers = useMemberDirectory({ enabled: loadInviteRoster });

  const channels = useQuery({
    queryKey: ['workspace', team, 'channels'],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.workspace.listChannels({ signal })).data,
  });

  const modules = useQuery({
    queryKey: ['workspace', team, 'modules'],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.workspace.listModules({ signal })).data,
  });

  const standups = useQuery({
    queryKey: ['workspace', team, 'standups'],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.standups.listStandups({ signal })).data,
  });

  async function invalidate() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['workspace', team, 'members'] }),
      client.invalidateQueries({ queryKey: ['session'] }),
    ]);
  }

  const role = useMutation({
    mutationFn: ({ id, role }: { id: string; role: 'admin' | 'member' }) =>
      api.members.updateMemberRole({ userId: id }, { role }),
    onSuccess: invalidate,
  });

  const grant = useMutation({
    mutationFn: ({
      id,
      module,
      enabled,
    }: {
      id: string;
      module: string;
      enabled: boolean;
    }) =>
      enabled
        ? api.members.grantModuleAdmin({ userId: id, module })
        : api.members.revokeModuleAdmin({ userId: id, module }),
    onSuccess: invalidate,
  });

  const invite = useMutation({
    mutationFn: (data: Parameters<typeof api.members.inviteMember>[0]) =>
      api.members.inviteMember(data),
    onSuccess: invalidate,
  });

  return {
    members,
    inviteMembers,
    channels,
    modules,
    standups,
    role,
    grant,
    invite,
    session,
  };
}
