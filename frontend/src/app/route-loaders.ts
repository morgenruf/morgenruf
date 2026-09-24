import { noop } from '@tanstack/react-query';
import { redirect } from '@tanstack/react-router';

import {
  analyticsOptions,
  channelsOptions,
  memberDirectoryOptions,
  modulesOptions,
  standupsOptions,
} from '@/common/api/queries';
import type { DashboardRouteMetadata } from '@/common/routing/metadata';
import { automationOptions } from '@/modules/automation/queries';
import {
  connectParticipationOptions,
  connectProgramsOptions,
  connectRoundsOptions,
  connectZoomOptions,
} from '@/modules/connect/queries';
import { insightsOptions } from '@/modules/insights/queries';
import {
  kudosConfigOptions,
  kudosFeedOptions,
  kudosGiversOptions,
  kudosReceiversOptions,
} from '@/modules/kudos/queries';
import { mcpKeysOptions } from '@/modules/mcp/queries';
import { reportsOptions } from '@/modules/reports/queries';
import { standupTemplatesOptions } from '@/modules/standups/queries';
import { todayOptions } from '@/modules/today/queries';
import {
  webhookEventsOptions,
  webhooksOptions,
} from '@/modules/webhooks/queries';

import type { AuthenticatedContext } from './router-context';

/** Resolve capabilities before page requests; components retain their explanatory gates. */
export function capabilityGuard(requirement: DashboardRouteMetadata) {
  return async ({
    context,
    abortController,
  }: {
    context: AuthenticatedContext;
    abortController: AbortController;
  }) => {
    const { services, session } = context;
    const generation = services.getSessionGeneration();

    if (services.isSignedOut())
      throw redirect({ to: '/dashboard/login', replace: true });

    if (
      abortController.signal.aborted ||
      services.getIdentity() !== `${session.team_id}:${session.user_id}`
    )
      return { capabilityAllowed: false };

    let capabilityAllowed = true;

    if (requirement.module) {
      try {
        const modules = await services.queryClient.fetchQuery(
          modulesOptions(services, session.team_id),
        );
        const feature = modules.find(
          (item) => item.name === requirement.module,
        );

        capabilityAllowed =
          !!feature?.available &&
          (requirement.requireActive === false ||
            (!!feature.active && !feature.missing_scopes.length));
      } catch {
        if (services.isSignedOut())
          throw redirect({ to: '/dashboard/login', replace: true });

        // The existing gate renders the Query error and offers a section-level retry.
        capabilityAllowed = false;
      }
    }

    if (requirement.administration)
      capabilityAllowed &&=
        session.role === 'admin' ||
        session.module_admin.includes(requirement.administration);

    capabilityAllowed &&=
      !abortController.signal.aborted &&
      generation === services.getSessionGeneration() &&
      services.getIdentity() === `${session.team_id}:${session.user_id}`;

    return { capabilityAllowed };
  };
}

export function prefetchDashboard(
  context: AuthenticatedContext,
  page: string,
  deps: {
    days?: number;
    program?: string;
    channel?: string;
    date_from?: string;
    date_to?: string;
    user_id?: string;
    programId?: string;
  } = {},
  signal?: AbortSignal,
) {
  if (context.capabilityAllowed === false) return;

  const { services, session } = context;
  const generation = services.getSessionGeneration();
  const isCurrent = () =>
    !signal?.aborted &&
    !services.isSignedOut() &&
    generation === services.getSessionGeneration() &&
    services.getIdentity() === `${session.team_id}:${session.user_id}`;

  if (!isCurrent()) return;

  const team = session.team_id;
  const client = services.queryClient;
  const directory = () =>
    void client.query(memberDirectoryOptions(services, team)).catch(noop);
  const channels = () =>
    void client.query(channelsOptions(services, team)).catch(noop);

  switch (page) {
    case 'today':
      void client.query(todayOptions(services, team)).catch(noop);
      directory();
      break;

    case 'standups':
      void client.query(standupsOptions(services, team)).catch(noop);
      void client.query(analyticsOptions(services, team, 14)).catch(noop);
      void client.query(standupTemplatesOptions(services, team)).catch(noop);
      directory();
      channels();
      break;

    case 'connect':
    case 'connectDetail':
    case 'connectAttendance': {
      void client.query(connectProgramsOptions(services, team)).catch(noop);

      if (page === 'connect') {
        channels();
        void client.query(connectZoomOptions(services, team)).catch(noop);
      }

      // The selected program is data-dependent, but must not delay the route.
      void client
        .ensureQueryData(connectProgramsOptions(services, team))
        .then((programs) => {
          if (!isCurrent()) return;

          if (page === 'connectDetail') {
            if (
              programs.some((program) => String(program.id) === deps.programId)
            ) {
              channels();
              void client.query(connectZoomOptions(services, team)).catch(noop);
            }

            return;
          }

          const selected =
            programs.find((program) => String(program.id) === deps.program) ??
            programs[0];

          if (selected) {
            void client
              .query(connectRoundsOptions(services, team, selected.id))
              .catch(noop);
            void client
              .query(connectParticipationOptions(services, team, selected.id))
              .catch(noop);
            directory();
          }
        })
        .catch(() => {
          /* The program query owns its visible error. */
        });
      break;
    }

    case 'connectNew':
      channels();
      void client.query(connectZoomOptions(services, team)).catch(noop);
      break;

    case 'settings':
      void client.query(standupsOptions(services, team)).catch(noop);
      void client.query(modulesOptions(services, team)).catch(noop);
      break;

    case 'insights':
      void client.query(insightsOptions(services, team)).catch(noop);
      directory();
      break;

    case 'reports': {
      const filters = {
        date_from: deps.date_from || undefined,
        date_to: deps.date_to || undefined,
        user_id: deps.user_id || undefined,
      };

      if (
        !filters.date_from ||
        !filters.date_to ||
        filters.date_from <= filters.date_to
      )
        void client.query(reportsOptions(services, team, filters)).catch(noop);

      directory();
      break;
    }

    case 'analytics':
      void client
        .query(analyticsOptions(services, team, deps.days ?? 7))
        .catch(noop);
      directory();
      break;

    case 'members':
      void client
        .query(memberDirectoryOptions(services, team, deps.channel))
        .catch(noop);
      channels();
      void client.query(modulesOptions(services, team)).catch(noop);
      void client.query(standupsOptions(services, team)).catch(noop);
      break;

    case 'kudos':
      void client.query(kudosFeedOptions(services, team)).catch(noop);
      void client
        .query(kudosReceiversOptions(services, team, deps.days ?? 30))
        .catch(noop);
      void client
        .query(kudosGiversOptions(services, team, deps.days ?? 30))
        .catch(noop);
      void client.query(kudosConfigOptions(services, team)).catch(noop);
      directory();
      break;

    case 'automation':
      void client.query(automationOptions(services, team)).catch(noop);
      channels();
      break;

    case 'webhooks':
      void client.query(webhooksOptions(services, team)).catch(noop);
      void client.query(webhookEventsOptions(services, team)).catch(noop);
      break;

    case 'mcp':
      void client.query(mcpKeysOptions(services, team)).catch(noop);
      break;
  }
}
