import { useId } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import type { PulseSettingsInput } from '@/common/api/generated/data-contracts';
import { healthColors } from '@/common/components/evilcharts/chart-palette';
import { EvilLineChart } from '@/common/components/evilcharts/charts/recharts-line-chart';
import {
  ChartTooltip,
  ChartTooltipSurface,
} from '@/common/components/evilcharts/ui/recharts-tooltip';
import { LoadingTransition } from '@/common/components/loading-transition';
import { EmptyState, ErrorState, PageHeader } from '@/common/components/page';
import { TimezoneSelect } from '@/common/components/timezone-select';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import { Input } from '@/common/components/ui/input';
import { ScrollArea } from '@/common/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { applyApiErrors } from '@/common/forms/api-errors';
import { formatDate } from '@/common/lib/format';

import { usePulse } from '../hooks';
import { PulseSettingsSkeleton, PulseTrendSkeleton } from '../loading';
import { trendData } from '../trend-utils';

// 0 is Monday, as the scheduler counts.
const days = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
].map((label, value) => ({ value, label }));

const promises = [
  'Answers are not stored one by one: Morgenruf only keeps how many people picked each value, with no names and no times. Who answered is kept apart, only to stop a second answer and to send one reminder.',
  'Results show only as team averages, and only for a week at least 5 people answered. Below that the week shows as a gap.',
  'There is no free text: two taps on buttons, nothing to recognise someone by.',
  'Nobody, admins included, can see what one person said. There is no per person view or export.',
  'eNPS is asked every fourth week, starting with the first.',
];

type SettingsForm = {
  enabled: boolean;
  day_of_week: number;
  time: string;
  timezone: string;
  audience_channel_id: string;
};

const defaults: SettingsForm = {
  enabled: false,
  day_of_week: 4,
  time: '14:00',
  timezone: 'UTC',
  audience_channel_id: '',
};

const pad = (value: number) => String(value).padStart(2, '0');

type Point = ReturnType<typeof trendData>[number];

function RoundTooltip({ active, point }: { active?: boolean; point?: Point }) {
  if (!active || !point) return null;

  return (
    <ChartTooltipSurface className="min-w-44 p-3">
      <p className="font-medium">{formatDate(point.sent_on)}</p>
      <p className="mt-1 text-muted-foreground">
        {point.hidden
          ? 'Fewer than 5 answers, so nothing is shown'
          : `Mood ${point.mood?.toFixed(1) ?? 'n/a'} of 5`}
      </p>
      {!point.hidden && point.enps != null && (
        <p className="text-muted-foreground">eNPS {point.enps}</p>
      )}
      <p className="text-muted-foreground">
        {point.respondents} of {point.invited} answered
      </p>
    </ChartTooltipSurface>
  );
}

const moodConfig = { mood: { label: 'Mood', colors: healthColors('success') } };
const enpsConfig = { enps: { label: 'eNPS', colors: healthColors('warning') } };

function TrendCard() {
  const { trend } = usePulse();
  const data = trendData(trend.data ?? []);
  const hasMood = data.some((point) => point.mood != null);
  const hasEnps = data.some((point) => point.enps != null);

  const tooltip = (
    <ChartTooltip
      filterNull={false}
      content={({ active, label }) => (
        <RoundTooltip active={active} point={data[Number(label)]} />
      )}
      cursor={{ stroke: 'var(--border)' }}
    />
  );
  const xAxis = (
    <EvilLineChart.XAxis
      dataKey="index"
      padding={{ left: 18, right: 18 }}
      tickFormatter={(index) =>
        formatDate(data[Number(index)]?.sent_on, {
          day: 'numeric',
          month: 'short',
        })
      }
      tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
      tickLine={false}
      axisLine={false}
      minTickGap={24}
    />
  );

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Team mood by week</CardTitle>
        <CardDescription>
          Average of the 1 to 5 answers. Weeks with fewer than 5 answers stay
          gaps.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <LoadingTransition pending={trend.isPending}>
          {trend.isPending ? (
            <PulseTrendSkeleton />
          ) : trend.isError ? (
            <ErrorState
              error={trend.error}
              retry={() => void trend.refetch()}
            />
          ) : !data.length ? (
            <EmptyState
              title="No check-ins yet"
              description="Results appear here after the first weekly check-in that at least 5 people answer."
            />
          ) : (
            <div className="space-y-6">
              {hasMood ? (
                <div
                  className="h-64 min-w-0"
                  role="group"
                  aria-label="Team mood by week, from 1 to 5. Exact values are in View chart data below."
                >
                  <EvilLineChart
                    config={moodConfig}
                    className="aspect-auto h-full w-full min-w-0"
                    data={data}
                    chartProps={{
                      margin: { top: 12, right: 12, bottom: 4, left: 0 },
                    }}
                  >
                    <EvilLineChart.Grid
                      vertical={false}
                      stroke="var(--border)"
                    />
                    {xAxis}
                    <EvilLineChart.YAxis
                      domain={[1, 5]}
                      ticks={[1, 2, 3, 4, 5]}
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      width={32}
                    />
                    {tooltip}
                    <EvilLineChart.Line
                      dataKey="mood"
                      glowing
                      connectNulls={false}
                    >
                      <EvilLineChart.Dot variant="border" />
                      <EvilLineChart.ActiveDot variant="colored-border" />
                    </EvilLineChart.Line>
                  </EvilLineChart>
                </div>
              ) : (
                <div className="grid min-h-40 place-content-center rounded-lg bg-muted/30 px-5 text-center">
                  <p className="text-sm font-medium">
                    No week has 5 answers yet
                  </p>
                  <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                    Results stay hidden until at least 5 people answer, so
                    nobody's answer can be worked out.
                  </p>
                </div>
              )}

              {hasEnps && (
                <div
                  className="h-48 min-w-0"
                  role="group"
                  aria-label="eNPS by week, from minus 100 to 100. Asked every fourth week."
                >
                  <EvilLineChart
                    config={enpsConfig}
                    className="aspect-auto h-full w-full min-w-0"
                    data={data}
                    chartProps={{
                      margin: { top: 12, right: 12, bottom: 4, left: 0 },
                    }}
                  >
                    <EvilLineChart.Grid
                      vertical={false}
                      stroke="var(--border)"
                    />
                    {xAxis}
                    <EvilLineChart.YAxis
                      domain={[-100, 100]}
                      ticks={[-100, 0, 100]}
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      width={40}
                    />
                    {tooltip}
                    <EvilLineChart.Line dataKey="enps" connectNulls>
                      <EvilLineChart.Dot variant="border" />
                    </EvilLineChart.Line>
                  </EvilLineChart>
                </div>
              )}

              <details className="rounded-lg border">
                <summary className="cursor-pointer rounded-lg px-3 py-3 text-sm font-medium hover:bg-muted/50">
                  View chart data
                </summary>
                <ScrollArea
                  orientation="horizontal"
                  className="min-w-0 border-t px-3"
                >
                  <table className="w-full text-sm">
                    <caption className="sr-only">
                      Pulse results by week, oldest first
                    </caption>
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th scope="col" className="py-3 pr-3 font-medium">
                          Week of
                        </th>
                        <th scope="col" className="px-2 py-3 font-medium">
                          Mood
                        </th>
                        <th scope="col" className="px-2 py-3 font-medium">
                          eNPS
                        </th>
                        <th scope="col" className="px-2 py-3 font-medium">
                          Answered
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.map((point) => (
                        <tr
                          key={point.sent_on}
                          className="border-b last:border-0"
                        >
                          <th
                            scope="row"
                            className="py-3 pr-3 text-left font-normal"
                          >
                            {formatDate(point.sent_on)}
                          </th>
                          <td className="px-2 py-3 tabular-nums">
                            {point.hidden
                              ? 'Fewer than 5 answers'
                              : (point.mood?.toFixed(1) ?? 'n/a')}
                          </td>
                          <td className="px-2 py-3 tabular-nums">
                            {point.enps ?? 'n/a'}
                          </td>
                          <td className="px-2 py-3 tabular-nums">
                            {point.respondents} of {point.invited}
                            {point.rate != null && ` (${point.rate}%)`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </ScrollArea>
              </details>
            </div>
          )}
        </LoadingTransition>
      </CardContent>
    </Card>
  );
}

function StatusCard() {
  const { feature, modules, enable, isAdmin } = usePulse();

  if (modules.isPending || !feature || feature.active) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pulse is switched off</CardTitle>
        <CardDescription>
          {isAdmin
            ? 'Turn it on, then choose when the weekly check-in goes out below.'
            : 'A workspace admin can turn Pulse on.'}
        </CardDescription>
      </CardHeader>
      {isAdmin && (
        <CardContent>
          <Button
            disabled={enable.isPending}
            onClick={() =>
              enable.mutate(undefined, {
                onSuccess: () => toast.success('Pulse is on'),
              })
            }
          >
            {enable.isPending ? 'Turning on…' : 'Turn on Pulse'}
          </Button>
        </CardContent>
      )}
    </Card>
  );
}

function SettingsCard() {
  const { settings, channels, save, canEdit } = usePulse();
  const id = useId();

  const form = useForm<SettingsForm>({
    resetOptions: { keepDirtyValues: true },
    values: settings.data
      ? {
          enabled: settings.data.enabled,
          day_of_week: settings.data.day_of_week,
          time: `${pad(settings.data.hour)}:${pad(settings.data.minute)}`,
          timezone: settings.data.timezone,
          audience_channel_id: settings.data.audience_channel_id ?? '',
        }
      : defaults,
  });

  const audienceOptions = [
    { value: '', label: 'Everyone in the workspace' },
    ...(channels.data ?? []).map((channel) => ({
      value: channel.id,
      label: `People in #${channel.name}`,
    })),
  ];

  const submit = form.handleSubmit((data) => {
    const [hour, minute] = data.time.split(':').map(Number);
    const body: PulseSettingsInput = {
      enabled: data.enabled,
      day_of_week: data.day_of_week,
      hour,
      minute,
      timezone: data.timezone,
      audience_channel_id: data.audience_channel_id,
    };
    save.mutate(body, {
      onSuccess: () => toast.success('Pulse settings saved'),
      onError: (error) => applyApiErrors(error, form.setError),
    });
  });

  const errors = form.formState.errors;

  return (
    <Card>
      <CardHeader>
        <CardTitle>When and who</CardTitle>
        <CardDescription>
          The check-in arrives by DM. It stays open for three days, with one
          reminder to people who have not answered.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {settings.isError ? (
          <ErrorState
            error={settings.error}
            retry={() => void settings.refetch()}
          />
        ) : (
          <LoadingTransition pending={settings.isPending}>
            {settings.isPending ? (
              <PulseSettingsSkeleton />
            ) : (
              <form className="space-y-5" onSubmit={submit} noValidate>
                <fieldset
                  disabled={!canEdit || save.isPending}
                  className="min-w-0 space-y-5"
                >
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <input type="checkbox" {...form.register('enabled')} />
                    Send the weekly check-in
                  </label>

                  <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
                    <Controller
                      control={form.control}
                      name="day_of_week"
                      render={({ field }) => (
                        <div className="flex flex-col gap-2 text-sm font-medium">
                          <span id={`${id}-day`}>Day</span>
                          <Select
                            name={field.name}
                            value={field.value}
                            items={days}
                            onValueChange={(value) => {
                              if (value !== null) field.onChange(Number(value));
                            }}
                          >
                            <SelectTrigger
                              className="w-full"
                              aria-labelledby={`${id}-day`}
                              ref={field.ref}
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {days.map((day) => (
                                <SelectItem key={day.value} value={day.value}>
                                  {day.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}
                    />

                    <div className="flex flex-col gap-2 text-sm font-medium">
                      <label htmlFor={`${id}-time`}>Time</label>
                      <Input
                        id={`${id}-time`}
                        type="time"
                        aria-invalid={!!errors.time}
                        {...form.register('time', {
                          required: 'Choose a time.',
                          pattern: {
                            value: /^([01]\d|2[0-3]):[0-5]\d$/,
                            message: 'Choose a time.',
                          },
                        })}
                      />
                    </div>

                    <Controller
                      control={form.control}
                      name="timezone"
                      rules={{ required: 'Choose a timezone.' }}
                      render={({ field, fieldState }) => (
                        <div className="flex flex-col gap-2 text-sm font-medium">
                          <span id={`${id}-tz`}>Timezone</span>
                          <TimezoneSelect
                            name={field.name}
                            value={field.value || undefined}
                            onValueChange={field.onChange}
                            ref={field.ref}
                            onBlur={field.onBlur}
                            aria-invalid={fieldState.invalid}
                            aria-describedby={`${id}-tz`}
                            disabled={!canEdit || save.isPending}
                          />
                        </div>
                      )}
                    />

                    <Controller
                      control={form.control}
                      name="audience_channel_id"
                      render={({ field }) => (
                        <div className="flex flex-col gap-2 text-sm font-medium">
                          <span id={`${id}-who`}>Who is asked</span>
                          <Select
                            name={field.name}
                            value={field.value}
                            items={audienceOptions}
                            onValueChange={(value) => {
                              if (value !== null) field.onChange(value);
                            }}
                          >
                            <SelectTrigger
                              className="w-full"
                              aria-labelledby={`${id}-who`}
                              ref={field.ref}
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {audienceOptions.map((item) => (
                                <SelectItem key={item.value} value={item.value}>
                                  {item.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}
                    />
                  </div>
                </fieldset>

                {Object.entries(errors).map(
                  ([field, error]) =>
                    field !== 'root' &&
                    typeof error?.message === 'string' &&
                    error.message && (
                      <p
                        key={field}
                        role="alert"
                        className="text-sm text-destructive"
                      >
                        {error.message}
                      </p>
                    ),
                )}
                {errors.root?.server && (
                  <p role="alert" className="text-sm text-destructive">
                    {errors.root.server.message}
                  </p>
                )}

                {canEdit && (
                  <Button type="submit" disabled={save.isPending}>
                    {save.isPending ? 'Saving…' : 'Save settings'}
                  </Button>
                )}
              </form>
            )}
          </LoadingTransition>
        )}
      </CardContent>
    </Card>
  );
}

function PrivacyCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>How answers stay anonymous</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
          {promises.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export default function PulsePage() {
  return (
    <div className="page">
      <PageHeader
        title="Pulse"
        description="A weekly anonymous check-in, shown only as team averages."
      />
      <StatusCard />
      <TrendCard />
      <div className="grid gap-5 lg:grid-cols-2">
        <SettingsCard />
        <PrivacyCard />
      </div>
    </div>
  );
}
