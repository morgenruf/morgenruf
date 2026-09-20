import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/common/api/client';
import { useSession } from '@/common/auth/use-session';

export type RuleInput = Parameters<typeof api.automation.createRule>[0];

export function useAutomation() {
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const key = ['workspace', team, 'automation'];

  const rules = useQuery({
    queryKey: key,
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.automation.listRules({ signal })).data,
  });

  const channels = useQuery({
    queryKey: ['workspace', team, 'channels'],
    enabled: !!team,
    queryFn: async ({ signal }) =>
      (await api.workspace.listChannels({ signal })).data,
  });

  const refresh = () => client.invalidateQueries({ queryKey: key });

  const create = useMutation({
    mutationFn: (data: RuleInput) => api.automation.createRule(data),
    onSuccess: refresh,
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.automation.deleteRule({ ruleId: id }),
    onSuccess: refresh,
  });

  return {
    rules,
    channels,
    create,
    remove,
    canEdit:
      session?.role === 'admin' || !!session?.module_admin?.includes('standup'),
  };
}
