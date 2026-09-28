import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { MemberProfile } from '@/common/api/generated/data-contracts';
import { myProfileOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

export function useMyProfile() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const profile = useQuery(myProfileOptions(services, team));

  const save = useMutation({
    mutationFn: (data: MemberProfile) => api.profile.updateMyProfile(data),
    onSuccess: (response) => {
      client.setQueryData(
        myProfileOptions(services, team).queryKey,
        response.data,
      );
      void client.invalidateQueries({
        queryKey: ['workspace', team, 'profile'],
      });
    },
  });

  return { profile, save, session };
}
