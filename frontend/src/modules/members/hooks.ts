import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import type {
  MemberProfile,
  ProfileImportInput,
} from '@/common/api/generated/data-contracts';
import {
  channelsOptions,
  modulesOptions,
  profilesOptions,
  standupsOptions,
} from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useMemberDirectory } from '@/common/api/use-member-directory';
import { useSession } from '@/common/auth/use-session';

export function useMembers(channel?: string, loadInviteRoster = false) {
  const services = useServices();
  const { api } = services;

  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();

  const members = useMemberDirectory({ channel });
  const inviteMembers = useMemberDirectory({ enabled: loadInviteRoster });

  const channels = useQuery(channelsOptions(services, team));
  const modules = useQuery(modulesOptions(services, team));
  const standups = useQuery(standupsOptions(services, team));

  async function invalidate() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['workspace', team, 'members'] }),
      client.invalidateQueries({ queryKey: ['session'] }),
    ]);

    services.invalidateRouter();
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
    mutationFn: (data: Parameters<Api['members']['inviteMember']>[0]) =>
      api.members.inviteMember(data),
    onSuccess: invalidate,
  });

  // Birthdays and start dates are for workspace admins only; the endpoint
  // refuses everyone else, so the query is not even sent for them.
  const isAdmin = session?.role === 'admin';
  const profiles = useQuery(profilesOptions(services, team, isAdmin));

  const invalidateProfiles = () =>
    client.invalidateQueries({ queryKey: ['workspace', team, 'profile'] });

  const saveProfile = useMutation({
    mutationFn: ({ id, data }: { id: string; data: MemberProfile }) =>
      api.profile.updateProfile({ userId: id }, data),
    onSuccess: invalidateProfiles,
  });

  const importDates = useMutation({
    mutationFn: (data: ProfileImportInput) => api.profile.importProfiles(data),
    onSuccess: (response) => {
      if (!response.data.preview) void invalidateProfiles();
    },
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
    profiles,
    saveProfile,
    importDates,
  };
}
