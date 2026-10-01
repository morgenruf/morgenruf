import type { DashboardRouteMetadata } from '@/common/routing/metadata';
import { AnalyticsPageSkeleton } from '@/modules/analytics/loading';
import { AutomationPageSkeleton } from '@/modules/automation/loading';
import { CelebrationsPageSkeleton } from '@/modules/celebrations/loading';
import {
  ConnectAttendancePageSkeleton,
  ConnectDetailPageSkeleton,
  ConnectListPageSkeleton,
  ConnectNewPageSkeleton,
} from '@/modules/connect/loading';
import { InsightsPageSkeleton } from '@/modules/insights/loading';
import { KudosPageSkeleton } from '@/modules/kudos/loading';
import { McpPageSkeleton } from '@/modules/mcp/loading';
import { MembersPageSkeleton } from '@/modules/members/loading';
import { PollsPageSkeleton } from '@/modules/polls/loading';
import { ProfilePageSkeleton } from '@/modules/profile/loading';
import { PulsePageSkeleton } from '@/modules/pulse/loading';
import { ReportsPageSkeleton } from '@/modules/reports/loading';
import { SettingsPageSkeleton } from '@/modules/settings/loading';
import { StandupsPageSkeleton } from '@/modules/standups/loading';
import { TodayPageSkeleton } from '@/modules/today/loading';
import { WebhooksPageSkeleton } from '@/modules/webhooks/loading';

export const dashboardViews = {
  today: {
    title: 'Today',
    Skeleton: TodayPageSkeleton,
    module: 'insights',
    requireActive: false,
  },

  standups: {
    title: 'Standups',
    Skeleton: StandupsPageSkeleton,
    module: 'standup',
  },

  connect: {
    title: 'Coffee chats',
    Skeleton: ConnectListPageSkeleton,
    module: 'connect',
    customGate: true,
  },

  connectNew: {
    title: 'New coffee chat',
    Skeleton: ConnectNewPageSkeleton,
    module: 'connect',
    customGate: true,
    administration: 'connect',
  },

  connectAttendance: {
    title: 'Attendance',
    Skeleton: ConnectAttendancePageSkeleton,
    module: 'connect',
    customGate: true,
  },

  connectDetail: {
    title: 'Coffee chat',
    Skeleton: ConnectDetailPageSkeleton,
    module: 'connect',
    customGate: true,
  },

  settings: { title: 'Settings', Skeleton: SettingsPageSkeleton },

  insights: {
    title: 'Insights',
    Skeleton: InsightsPageSkeleton,
    module: 'insights',
  },

  reports: { title: 'Reports', Skeleton: ReportsPageSkeleton },

  analytics: { title: 'Analytics', Skeleton: AnalyticsPageSkeleton },

  members: { title: 'Members', Skeleton: MembersPageSkeleton },

  profile: { title: 'My profile', Skeleton: ProfilePageSkeleton },

  kudos: { title: 'Kudos', Skeleton: KudosPageSkeleton, module: 'kudos' },

  polls: { title: 'Polls', Skeleton: PollsPageSkeleton, module: 'polls' },

  // Reachable while switched off, so an admin can turn it on from the page.
  pulse: {
    title: 'Pulse',
    Skeleton: PulsePageSkeleton,
    module: 'pulse',
    requireActive: false,
  },

  // Reachable while switched off, so HR can set it up before an admin turns
  // it on. The page explains its own state.
  celebrations: {
    title: 'Celebrations',
    Skeleton: CelebrationsPageSkeleton,
    module: 'celebrations',
    requireActive: false,
  },

  automation: {
    title: 'Automation',
    Skeleton: AutomationPageSkeleton,
    module: 'standup',
  },

  webhooks: { title: 'Webhooks', Skeleton: WebhooksPageSkeleton },

  mcp: { title: 'MCP', Skeleton: McpPageSkeleton, module: 'mcp' },
} satisfies Record<string, DashboardRouteMetadata>;
