import { getRouteApi, useLocation } from '@tanstack/react-router';
import { Plus, Search, X } from 'lucide-react';

import { usePermissions } from '@/common/auth/use-session';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { Button } from '@/common/components/ui/button';
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/common/components/ui/input-group';
import { Tabs, TabsList, TabsTrigger } from '@/common/components/ui/tabs';

import { sortedStandups } from './form-utils';
import { useStandupHealth, useStandupResources, useStandups } from './hooks';
import { StandupsSkeleton } from './loading';
import { validateSearch, type Search as StandupsSearch } from './search';
import { StandupEditor } from './standup-editor';
import { StandupRow } from './standup-row';

export function StandupsPage() {
  const query = useStandups();
  const health = useStandupHealth();
  const { channels } = useStandupResources();

  const { canAdminister } = usePermissions();
  const editable = canAdminister('standup');

  const route = getRouteApi('/dashboard/_authenticated/standups');
  const params = route.useSearch();
  const navigate = route.useNavigate();

  // Route search commits after loaders; typing needs the latest URL immediately.
  const search = useLocation({
    select: (location) => validateSearch.shape.q.parse(location.search.q),
  });

  const status = params.status;
  const selected = params.edit;
  const creating = params.new;

  const editing = query.data?.find((item) => String(item.id) === selected);
  const all = query.data ?? [];

  const channelNames = new Map(
    channels.data?.map((channel) => [channel.id, channel.name]),
  );
  const metrics = new Map(
    health.data?.schedules?.map((row) => [row.schedule_id, row]),
  );

  const needle = search.trim().toLowerCase();
  const filtered = sortedStandups(all).filter(
    (standup) =>
      (!status || standup.active === (status === 'active')) &&
      `${standup.name} #${channelNames.get(standup.channel_id) ?? standup.channel_id}`
        .toLowerCase()
        .includes(needle),
  );

  const updateParams = (
    values: Partial<Record<keyof StandupsSearch, string | null>>,
    replace = false,
  ) =>
    void navigate({
      search: (previous) => validateSearch.parse({ ...previous, ...values }),
      replace,
      resetScroll: false,
    });
  const openNew = () => updateParams({ new: 'true', edit: null });

  return (
    <div className="page">
      <PageHeader
        title="Standups"
        reserveActionSpace
        description="Your team’s check-ins, at a glance."
        actions={
          editable && (
            <Button onClick={openNew}>
              <Plus className="size-4" />
              New standup
            </Button>
          )
        }
      />

      <LoadingTransition pending={query.isPending}>
        {query.isPending ? (
          <StandupsSkeleton />
        ) : query.error && !query.data ? (
          <ErrorState error={query.error} retry={() => query.refetch()} />
        ) : !all.length ? (
          <EmptyState
            title="Your first standup starts here"
            description="Choose a channel, a few questions, and a time that works for your team."
            action={
              editable && <Button onClick={openNew}>Create standup</Button>
            }
          />
        ) : (
          <div className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <Tabs
                value={status}
                onValueChange={(value) =>
                  updateParams({ status: String(value) })
                }
              >
                <TabsList aria-label="Filter standups by status">
                  {[
                    { value: '', label: 'All', count: all.length },
                    {
                      value: 'active',
                      label: 'Active',
                      count: all.filter((s) => s.active).length,
                    },
                    {
                      value: 'paused',
                      label: 'Paused',
                      count: all.filter((s) => !s.active).length,
                    },
                  ].map((item) => (
                    <TabsTrigger
                      key={item.value}
                      value={item.value}
                      aria-label={`${item.label} ${item.count}`}
                    >
                      {item.label}
                      <span className="text-xs text-muted-foreground">
                        {item.count}
                      </span>
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <InputGroup className="w-full sm:w-64">
                <InputGroupAddon>
                  <Search aria-hidden="true" />
                </InputGroupAddon>
                <InputGroupInput
                  aria-label="Search standups"
                  placeholder="Search name or channel…"
                  value={search}
                  onChange={(event) =>
                    updateParams({ q: event.target.value }, true)
                  }
                />
                {search && (
                  <InputGroupAddon align="inline-end">
                    <InputGroupButton
                      aria-label="Clear standup search"
                      size="icon-xs"
                      onClick={() => updateParams({ q: null }, true)}
                    >
                      <X />
                    </InputGroupButton>
                  </InputGroupAddon>
                )}
              </InputGroup>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <p role="status">
                {filtered.length === all.length
                  ? `${all.length} standup${all.length === 1 ? '' : 's'}`
                  : `${filtered.length} of ${all.length} standups`}{' '}
                · earliest time first
              </p>
              <p>Participation · last 14 days</p>
            </div>
            {query.error && (
              <ErrorState error={query.error} retry={() => query.refetch()} />
            )}
            {health.isError && (
              <div
                role="alert"
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-card px-4 py-2 text-sm"
              >
                <span>Participation unavailable</span>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={health.isFetching}
                  onClick={() => health.refetch()}
                >
                  {health.isFetching ? 'Retrying…' : 'Retry participation'}
                </Button>
              </div>
            )}
            {filtered.length ? (
              <ul
                aria-label="Standup schedules"
                className="divide-y rounded-xl border bg-card"
              >
                {filtered.map((standup) => (
                  <StandupRow
                    key={standup.id}
                    standup={standup}
                    channel={channelNames.get(standup.channel_id)}
                    metrics={metrics.get(standup.id)}
                    healthPending={health.isPending}
                    healthUnavailable={health.isError}
                    editable={editable}
                    onEdit={() =>
                      updateParams({ edit: String(standup.id), new: null })
                    }
                  />
                ))}
              </ul>
            ) : (
              <EmptyState
                title="No matching standups"
                description="Try another name, channel, or status."
                action={
                  <Button
                    variant="outline"
                    onClick={() => updateParams({ q: null, status: null })}
                  >
                    Clear filters
                  </Button>
                }
              />
            )}
          </div>
        )}
      </LoadingTransition>

      {editable && query.data && (creating || editing) && (
        <StandupEditor
          key={editing?.id ?? 'new'}
          standup={editing}
          workspace={editing ?? query.data[0]}
          close={() => updateParams({ edit: null, new: null })}
        />
      )}
    </div>
  );
}

export default StandupsPage;
