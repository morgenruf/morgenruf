import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Api } from '@/common/api/client';
import { channelsOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import { automationOptions } from './queries';

export type RuleInput = Parameters<Api['automation']['createRule']>[0];

export function useAutomation() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;

  const client = useQueryClient();
  const key = ['workspace', team, 'automation'];

  const rules = useQuery(automationOptions(services, team));
  const channels = useQuery(channelsOptions(services, team));

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
