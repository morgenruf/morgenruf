import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PulseSettingsInput } from '@/common/api/generated/data-contracts';
import { channelsOptions, modulesOptions } from '@/common/api/queries';
import { useServices } from '@/common/api/services-context';
import { useSession } from '@/common/auth/use-session';

import { pulseSettingsOptions, pulseTrendOptions } from './queries';

export function usePulse() {
  const services = useServices();
  const { api } = services;
  const { data: session } = useSession();
  const team = session?.team_id;
  const isAdmin = session?.role === 'admin';
  const canEdit = isAdmin || !!session?.module_admin?.includes('pulse');

  const client = useQueryClient();
  const settings = useQuery(pulseSettingsOptions(services, team));
  const trend = useQuery(pulseTrendOptions(services, team));
  const channels = useQuery(channelsOptions(services, team));
  const modules = useQuery(modulesOptions(services, team));
  const feature = modules.data?.find((item) => item.name === 'pulse');

  const save = useMutation({
    // The form shows this error inline; skip the global toast.
    meta: { silent: true },
    mutationFn: (data: PulseSettingsInput) =>
      api.pulse.updatePulseSettings(data),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ['workspace', team, 'pulse'] }),
  });

  const enable = useMutation({
    mutationFn: () =>
      api.workspace.updateModule({ name: 'pulse' }, { enabled: true }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ['workspace', team, 'modules'] }),
  });

  return {
    settings,
    trend,
    channels,
    modules,
    feature,
    active: !!feature?.active,
    save,
    enable,
    canEdit,
    isAdmin,
  };
}
