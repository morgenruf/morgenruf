/* eslint-disable */
/* tslint:disable */
// @ts-nocheck
/*
 * ---------------------------------------------------------------
 * ## THIS FILE WAS GENERATED VIA SWAGGER-TYPESCRIPT-API        ##
 * ##                                                           ##
 * ## AUTHOR: acacode                                           ##
 * ## SOURCE: https://github.com/acacode/swagger-typescript-api ##
 * ---------------------------------------------------------------
 */

export interface AnalyticsData {
  completed: number;
  completion_rate: number;
  days: number;
  enrolled_members: number;
  expected: number;
  members: ParticipationMember[];
  missed: number;
  on_vacation_members: number;
  schedules: ScheduleParticipation[];
  unenrolled_members: number;
  window_days: string[];
}

export interface ApiError {
  details?: Record<string, string[]>;
  error: string;
}

export interface AutomationRule {
  action: string;
  action_message: string | null;
  action_target: string;
  active: boolean;
  condition_value: string | null;
  /** @format date-time */
  created_at: string;
  id: number;
  name: string;
  team_id: string;
  trigger: string;
}

export interface AutomationRuleInput {
  action: string;
  action_message?: string | null;
  action_target: string;
  condition_value?: string | null;
  name: string;
  trigger: string;
}

export interface AwaitingResponse {
  real_name: string | null;
  user_id: string;
}

export interface BlockedResponse {
  blockers: string;
  real_name: string | null;
  /** @format date-time */
  submitted_at: string | null;
  user_id: string;
}

export interface Channel {
  id: string;
  name: string;
}

export interface ConnectMatch {
  /** @format date-time */
  agreed_at: string | null;
  /** @format date-time */
  delivered_at: string | null;
  has_zoom: boolean;
  id: number;
  members: string[];
  /** @format date-time */
  nudged_at: string | null;
  status: string;
}

export interface ConnectMember {
  avatar: string;
  eligible: boolean;
  name: string;
  paired: number;
  state: string;
  /** @format date */
  until: string | null;
  user_id: string;
}

export interface ConnectMemberInput {
  state: "in" | "out" | "snoozed";
  /**
   * @min 1
   * @max 52
   */
  weeks?: number;
}

export interface ConnectMemberState {
  state: string;
  /** @format date */
  until: string | null;
  user_id: string;
}

export interface ConnectParticipation {
  /** @format date-time */
  last_met: string | null;
  met: number;
  missed: number;
  no_reply: number;
  paired: number;
  user_id: string;
}

export interface ConnectProgram {
  channel_id: string;
  /** @format date-time */
  created_at: string | null;
  day_of_week: number;
  enabled: boolean;
  group_size: number;
  hour: number;
  id: number;
  interval_weeks: number;
  intro_tone: string;
  /** @format date-time */
  last_round?: string | null;
  match_working_hours: boolean;
  meeting_link: string | null;
  meeting_minutes: number;
  minute: number;
  name: string;
  /** @format date */
  next_round_date: string | null;
  pool_size?: number | null;
  post_stats: boolean;
  round_count?: number;
  strict_group_size: boolean;
  suggest_times: boolean;
  team_id: string;
  timezone: string;
  /** @format date */
  upcoming_round?: string | null;
  use_icebreaker: boolean;
  video_mode: string;
}

export interface ConnectRound {
  agreed: number;
  /** @format date-time */
  created_at: string | null;
  id: number;
  matches: number;
  member_count: number;
  met: number;
  missed: number;
  no_reply: number;
  program_id: number;
  rematch_requests: number;
  /** @format date-time */
  scheduled_for: string;
  state: string;
  team_id: string;
  undelivered: number;
  with_zoom: number;
}

export interface ConnectRunStarted {
  round: number | null;
  started: boolean;
}

export type CreateFeedTokenError = ApiError;

export type CreateKeyError = ApiError;

export type CreateProgramError = ApiError;

export type CreateRuleError = ApiError;

export type CreateStandupError = ApiError;

export type CreateWebhookError = ApiError;

export interface CreatedId {
  id: number;
}

export type DeleteFeedTokenError = ApiError;

export type DeleteProgramError = ApiError;

export interface DeleteProgramParams {
  /** @min 0 */
  programId: number;
}

export type DeleteRuleError = ApiError;

export interface DeleteRuleParams {
  /** @min 0 */
  ruleId: number;
}

export type DeleteStandupError = ApiError;

export interface DeleteStandupParams {
  /** @min 0 */
  standupId: number;
}

export type DeleteWebhookError = ApiError;

export interface DeleteWebhookParams {
  /** @minLength 1 */
  hookId: string;
}

export interface DeletedProgram {
  deleted: number;
}

export type ExportCsvError = ApiError;

export interface ExportCsvParams {
  from?: string;
  to?: string;
}

export interface FeedToken {
  token: string;
  url: string;
}

export type GetAnalyticsError = ApiError;

export interface GetAnalyticsParams {
  /**
   * @min 1
   * @max 365
   */
  days?: number;
}

export type GetConfigError = ApiError;

export type GetFeedError = ApiError;

export interface GetFeedParams {
  /** @minLength 1 */
  token: string;
}

export type GetGiversError = ApiError;

export interface GetGiversParams {
  /**
   * @min 1
   * @max 365
   */
  days?: number;
}

export type GetInsightsError = ApiError;

export interface GetInsightsParams {
  /**
   * @min 7
   * @max 90
   */
  days?: number;
  /**
   * @min 2
   * @max 10
   */
  min_blocker_days?: number;
}

export type GetLeaderboardError = ApiError;

export interface GetLeaderboardParams {
  /**
   * @min 1
   * @max 365
   */
  days?: number;
}

export type GetReportsError = ApiError;

export interface GetReportsParams {
  date_from?: string;
  date_to?: string;
  user_id?: string;
}

export type GetSessionError = ApiError;

export type GetStatsError = ApiError;

export type GetTodayError = ApiError;

export interface GetTodayParams {
  /**
   * @min 1
   * @max 20
   */
  kudos?: number;
}

export type GetWebhookEventsError = ApiError;

export type GetZoomError = ApiError;

export type GrantModuleAdminError = ApiError;

export interface GrantModuleAdminParams {
  /** @minLength 1 */
  module: string;
  /** @minLength 1 */
  userId: string;
}

export interface InsightsData {
  stuck: PersistentBlocker[];
  unrecognised: UnrecognisedContributor[];
  window_days: number;
}

export type InviteMemberError = ApiError;

export interface InviteMemberInput {
  /** @default "admin" */
  role?: "admin" | "member";
  user_id: string;
}

export interface KudosConfig {
  daily_allowance: number;
  emoji: string;
  token_auto: boolean;
}

export interface KudosConfigInput {
  /**
   * @min 0
   * @max 50
   * @default 5
   */
  daily_allowance?: number;
  /**
   * @minLength 1
   * @maxLength 16
   */
  emoji: string;
}

export interface KudosEntry {
  channel_id?: string | null;
  /** @format date-time */
  created_at: string;
  emoji?: string | null;
  from_name?: string | null;
  from_user: string;
  id: number;
  message: string;
  team_id?: string;
  to_name?: string | null;
  to_user: string;
}

export interface KudosGiver {
  given: number;
  /** @format date-time */
  last_given: string | null;
  user_id: string;
}

export interface KudosReceiver {
  /** @format date-time */
  last_kudos: string | null;
  received: number;
  to_user: string;
}

export type ListChannelsError = ApiError;

export type ListKeysError = ApiError;

export type ListKudosError = ApiError;

export interface ListKudosParams {
  /**
   * @min 1
   * @max 200
   */
  limit?: number;
}

export type ListMatchesError = ApiError;

export interface ListMatchesParams {
  /** @min 0 */
  roundId: number;
}

export type ListMembersError = ApiError;

export interface ListMembersParams {
  channel_id?: string;
}

export type ListModulesError = ApiError;

export type ListParticipationError = ApiError;

export interface ListParticipationParams {
  /** @min 0 */
  programId: number;
  /**
   * @min 1
   * @max 52
   */
  rounds?: number;
}

export type ListProgramMembersError = ApiError;

export interface ListProgramMembersParams {
  /** @min 0 */
  programId: number;
}

export type ListProgramsError = ApiError;

export type ListRoundsError = ApiError;

export interface ListRoundsParams {
  /** @min 0 */
  programId: number;
}

export type ListRulesError = ApiError;

export type ListStandupsError = ApiError;

export type ListTemplatesError = ApiError;

export type ListWebhookDeliveriesError = ApiError;

export interface ListWebhookDeliveriesParams {
  /** @minLength 1 */
  hookId: string;
  /**
   * @min 1
   * @max 200
   */
  limit?: number;
}

export type ListWebhooksError = ApiError;

export type LogoutError = ApiError;

export interface McpKey {
  active: boolean;
  /** @format date-time */
  created_at: string;
  id: number;
  key_prefix: string;
  /** @format date-time */
  last_used_at: string | null;
  name: string;
}

export interface McpKeyCreated {
  key: string;
  message: string;
}

export interface McpKeyInput {
  /** @default "Default" */
  name?: string;
}

export interface McpKeys {
  keys: McpKey[];
}

export interface Member {
  avatar: string;
  display_name: string;
  email: string | null;
  id: string;
  module_admin: string[];
  name: string | null;
  role: string;
  tracked: boolean;
  tz: string | null;
}

export interface MemberRole {
  name?: string;
  ok: boolean;
  role: string;
  user_id: string;
}

export interface ModuleGrant {
  granted: boolean;
  module: string;
  ok: boolean;
  user_id: string;
}

export interface ModuleInput {
  enabled: boolean;
}

export interface ModuleScopeError {
  error: string;
  reauthorise_url: string;
  required: string[];
}

export interface ModuleUpdated {
  enabled: boolean;
  module: string;
}

export interface NavigationItem {
  label: string;
  path: string;
}

export interface NextChat {
  /** @format date */
  date: string;
  days_away: number;
  name: string;
  overdue: boolean;
  program_id: number;
}

export interface Ok {
  ok: boolean;
}

export interface PaginationMetadata {
  /** First available page number. */
  first_page?: number;
  /** Last available page number. */
  last_page?: number;
  /** Next page number. */
  next_page?: number;
  /** Current page number. */
  page?: number;
  /** Previous page number. */
  previous_page?: number;
  /** Total number of items. */
  total?: number;
  /** Total number of pages. */
  total_pages?: number;
}

export interface ParticipationDay {
  blocked: boolean;
  completed: number;
  /** @format date */
  date: string;
  expected: number;
}

export interface ParticipationMember {
  completed: number;
  completion_rate: number;
  days: ParticipationDay[];
  days_with_blockers: number;
  enrolled: boolean;
  expected: number;
  /** @format date-time */
  last_standup: string | null;
  missed: number;
  on_vacation: boolean;
  real_name: string | null;
  responses: number;
  schedule_ids: number[];
  schedules: string[];
  user_id: string;
}

export interface ParticipationSummary {
  completed: number;
  completion_rate: number;
  days: number;
  enrolled_members: number;
  expected: number;
  missed: number;
  on_vacation_members: number;
  responding_members: number;
  responses: number;
  total_members: number;
  unenrolled_members: number;
}

export interface PersistentBlocker {
  days: number;
  /** @format date */
  first_seen: string;
  /** @format date */
  last_seen: string;
  real_name: string | null;
  text: string;
  user_id: string;
}

export interface ProgramInput {
  channel_id?: string;
  /**
   * @min 0
   * @max 6
   */
  day_of_week?: number;
  enabled?: boolean;
  /**
   * @min 2
   * @max 8
   */
  group_size?: number;
  /**
   * @min 0
   * @max 23
   */
  hour?: number;
  /**
   * @min 1
   * @max 8
   */
  interval_weeks?: number;
  intro_tone?: "hybrid" | "remote" | "in_person";
  match_working_hours?: boolean;
  /** @pattern ^(?:https?://.*)?$ */
  meeting_link?: string | null;
  meeting_minutes?: 15 | 30 | 45 | 60;
  /**
   * @min 0
   * @max 59
   */
  minute?: number;
  name?: string;
  /** @format date */
  next_round_date?: string | null;
  post_stats?: boolean;
  strict_group_size?: boolean;
  suggest_times?: boolean;
  timezone?: string;
  use_icebreaker?: boolean;
  video_mode?: "link" | "zoom" | "none";
}

export interface PublicFeed {
  /** @format date */
  date: string;
  standups: PublicFeedResponse[];
  title: string;
}

export interface PublicFeedResponse {
  blockers: string | null;
  has_blockers: boolean;
  /** @format date-time */
  submitted_at: string | null;
  today: string | null;
  user_id: string;
  user_name: string | null;
  yesterday: string | null;
}

export interface ReportParticipation {
  completed: number;
  completion_rate: number;
  enrolled: boolean;
  expected: number;
  name: string;
  on_vacation: boolean;
  responses: number;
  schedules: string[];
  stars: number;
  total: number;
  user_id: string;
}

export interface ReportsData {
  channel_names: Record<string, string>;
  participation: ReportParticipation[];
  schedules: ScheduleParticipation[];
  standups: StandupResponse[];
  summary: ParticipationSummary;
  total_days: number;
}

export type RevokeKeyError = ApiError;

export interface RevokeKeyParams {
  /** @min 0 */
  keyId: number;
}

export type RevokeModuleAdminError = ApiError;

export interface RevokeModuleAdminParams {
  /** @minLength 1 */
  module: string;
  /** @minLength 1 */
  userId: string;
}

export interface RoleInput {
  /** @default "member" */
  role?: "admin" | "member";
}

export type RotateWebhookSecretError = ApiError;

export interface RotateWebhookSecretParams {
  /** @minLength 1 */
  hookId: string;
}

export type RunProgramError = ApiError;

export interface RunProgramParams {
  /** @min 0 */
  programId: number;
}

export interface ScheduleParticipation {
  completed: number;
  completion_rate: number;
  expected: number;
  missed: number;
  name: string;
  occurrence_days: number;
  participants: number;
  schedule_id: number;
  series: (number | null)[];
}

export interface SessionInfo {
  csrf_token: string;
  mcp_endpoint: string;
  module_admin: string[];
  role: string;
  team_id: string;
  team_name: string;
  user_id: string;
}

export interface Standup {
  active: boolean;
  ai_provider: string;
  ai_summary_enabled: boolean;
  channel_id: string;
  digest_email: string;
  digest_enabled: boolean;
  display_avatar: boolean;
  edit_window: string;
  feed_public: boolean;
  feed_token: string;
  github_repo: string;
  group_by: string;
  id: number;
  jira_base_url: string;
  linear_team: string;
  manager_digest_enabled: boolean;
  manager_email: string;
  name: string;
  next_run: string;
  notify_on_report: boolean;
  nudge_minutes_before: number;
  nudge_missing: boolean;
  participants: string[];
  post_as: string;
  post_summary: boolean;
  post_to_thread: boolean;
  questions: string[];
  registration_error: string | null;
  reminder_minutes: number;
  report_channel: string;
  report_time: string;
  schedule_days: string[];
  schedule_time: string;
  schedule_tz: string;
  sort_order: string;
  zendesk_base_url: string;
}

export interface StandupInput {
  active?: boolean;
  ai_provider?: "openai" | "anthropic";
  ai_summary_enabled?: boolean;
  channel_id?: string;
  digest_email?: string;
  digest_enabled?: boolean;
  edit_window?: "report" | "4h" | "none";
  feed_public?: boolean;
  feed_token?: string;
  github_repo?: string;
  group_by?: string;
  jira_base_url?: string;
  linear_team?: string;
  manager_digest_enabled?: boolean;
  manager_email?: string;
  name?: string;
  notify_on_report?: boolean;
  /** @min 1 */
  nudge_minutes_before?: number;
  nudge_missing?: boolean;
  participants?: string[];
  post_summary?: boolean;
  post_to_thread?: boolean;
  questions?: string[];
  /** @min -1 */
  reminder_minutes?: number;
  report_channel?: string;
  report_time?: string;
  schedule_days?: ("mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun")[];
  schedule_time?: string;
  schedule_tz?: string;
}

export interface StandupResponse {
  blockers: string | null;
  has_blockers: boolean;
  id?: number;
  mood: string | null;
  questions?: string[] | null;
  real_name?: string | null;
  schedule_id: number | null;
  /** @format date */
  standup_date: string;
  /** @format date-time */
  submitted_at: string | null;
  team_id?: string;
  today: string | null;
  user_id: string;
  user_name?: string | null;
  yesterday: string | null;
}

export interface StandupTemplate {
  description: string;
  icon: string;
  id: string;
  name: string;
  questions: string[];
}

export interface Stats {
  active_members: number;
  completed_responses: number;
  completion_rate: number;
  days: number;
  enrolled_members: number;
  expected_responses: number;
  missed_responses: number;
  on_vacation_members: number;
  responses_this_week: number;
  schedules: ScheduleParticipation[];
  total_members: number;
  total_responses: number;
  unenrolled_members: number;
}

export type TestWebhookError = ApiError;

export interface TestWebhookParams {
  /** @minLength 1 */
  hookId: string;
}

export interface Today {
  awaiting: AwaitingResponse[];
  blocked: BlockedResponse[];
  counts: TodayCounts;
  /** @format date */
  date: string;
  kudos: KudosEntry[];
  next_chat: NextChat | null;
  responses: StandupResponse[];
}

export interface TodayCounts {
  answered: number;
  awaiting: number;
  blocked: number;
  expected: number;
}

export interface UnrecognisedContributor {
  kudos: number;
  /** @format date */
  last_standup: string | null;
  real_name: string | null;
  standups: number;
  user_id: string;
}

export type UpdateConfigError = ApiError;

export type UpdateMemberRoleError = ApiError;

export interface UpdateMemberRoleParams {
  /** @minLength 1 */
  userId: string;
}

export type UpdateModuleError = ApiError | ModuleScopeError;

export interface UpdateModuleParams {
  /** @minLength 1 */
  name: string;
}

export type UpdateProgramError = ApiError;

export type UpdateProgramMemberError = ApiError;

export interface UpdateProgramMemberParams {
  /** @min 0 */
  programId: number;
  /** @minLength 1 */
  userId: string;
}

export interface UpdateProgramParams {
  /** @min 0 */
  programId: number;
}

export type UpdateStandupError = ApiError;

export interface UpdateStandupParams {
  /** @min 0 */
  standupId: number;
}

export type UpdateWebhookError = ApiError;

export interface UpdateWebhookParams {
  /** @minLength 1 */
  hookId: string;
}

export interface Webhook {
  /** @format date-time */
  created_at: string | null;
  events: string[];
  has_secret: boolean;
  id: number;
  secret?: string;
  secret_prefix: string | null;
  secret_shown_once?: boolean;
  signed: boolean;
  url: string;
  webhook_url: string;
}

export interface WebhookDelivery {
  /** @format date-time */
  created_at: string;
  duration_ms: number;
  error: string | null;
  event_type: string;
  id: number;
  ok: boolean;
  signed: boolean;
  status_code: number | null;
  webhook_id: number;
}

export interface WebhookEvents {
  default: string[];
  events: string[];
}

export interface WebhookInput {
  events?: string[];
  url?: string;
}

export interface WebhookTest {
  duration_ms: number;
  error: string | null;
  event: string;
  ok: boolean;
  signed: boolean;
  status_code: number | null;
  webhook_id: number;
}

export interface WorkspaceModule {
  active: boolean;
  available: boolean;
  delegable: boolean;
  enabled: boolean;
  missing_scopes: string[];
  name: string;
  nav: NavigationItem[];
  required_scopes: string[];
}

export interface ZoomSummary {
  configured: boolean;
  linked: number;
  needs_reconnect: number;
}
