"""Backend-owned browser API contracts, shared by serialization and OpenAPI."""

from datetime import date, datetime, timedelta, timezone

from marshmallow import EXCLUDE, Schema, ValidationError, fields, pre_load, validate, validates_schema


class ApiSchema(Schema):
    class Meta:
        unknown = EXCLUDE


class ISOString(fields.String):
    """Serialize database dates and already-normalized ISO strings identically."""

    def _serialize(self, value, attr, obj, **kwargs):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return super()._serialize(value, attr, obj, **kwargs)


def string(**kwargs):
    return fields.String(required=True, **kwargs)


def integer(**kwargs):
    return fields.Integer(required=True, **kwargs)


def boolean(**kwargs):
    return fields.Boolean(required=True, **kwargs)


def strings(**kwargs):
    return fields.List(fields.String(), required=True, **kwargs)


def iso(kind="date-time", required=True, **kwargs):
    return ISOString(required=required, metadata={"format": kind}, **kwargs)


def nested(schema, many=False, **kwargs):
    return fields.Nested(schema, many=many, required=True, **kwargs)


def model(schema_name, **attributes):
    return type(schema_name, (ApiSchema,), attributes)


Error = model(
    "ApiError", error=string(), details=fields.Dict(keys=fields.String(), values=fields.List(fields.String()))
)
Ok = model("Ok", ok=boolean())
CreatedId = model("CreatedId", id=integer())
Session = model(
    "SessionInfo",
    team_id=string(),
    team_name=string(),
    user_id=string(),
    role=string(),
    module_admin=strings(),
    mcp_endpoint=string(),
    csrf_token=string(),
)
Channel = model("Channel", id=string(), name=string())
Member = model(
    "Member",
    id=string(),
    name=string(allow_none=True),
    display_name=string(),
    avatar=string(),
    email=string(allow_none=True),
    tz=string(allow_none=True),
    role=string(),
    module_admin=strings(),
    tracked=boolean(),
)
MemberRole = model("MemberRole", ok=boolean(), user_id=string(), role=string(), name=fields.String())
ModuleGrant = model("ModuleGrant", ok=boolean(), user_id=string(), module=string(), granted=boolean())
NavigationItem = model("NavigationItem", label=string(), path=string())
WorkspaceModule = model(
    "WorkspaceModule",
    name=string(),
    active=boolean(),
    enabled=boolean(),
    required_scopes=strings(),
    missing_scopes=strings(),
    available=boolean(),
    delegable=boolean(),
    nav=nested(NavigationItem, many=True),
)
ModuleUpdated = model("ModuleUpdated", module=string(), enabled=boolean())
ModuleScopeError = model("ModuleScopeError", error=string(), required=strings(), reauthorise_url=string())

Standup = model(
    "Standup",
    **{
        **{
            key: string()
            for key in (
                "name",
                "channel_id",
                "schedule_time",
                "schedule_tz",
                "report_channel",
                "digest_email",
                "report_time",
                "group_by",
                "post_as",
                "sort_order",
                "edit_window",
                "jira_base_url",
                "zendesk_base_url",
                "github_repo",
                "linear_team",
                "ai_provider",
                "feed_token",
                "manager_email",
                "next_run",
            )
        },
        **{
            key: boolean()
            for key in (
                "active",
                "digest_enabled",
                "nudge_missing",
                "display_avatar",
                "ai_summary_enabled",
                "feed_public",
                "manager_digest_enabled",
                "post_to_thread",
                "notify_on_report",
                "post_summary",
                "sync_with_channel",
            )
        },
        "id": integer(),
        "schedule_days": strings(),
        "questions": strings(),
        "participants": strings(),
        "reminder_minutes": integer(),
        "nudge_minutes_before": integer(),
        "registration_error": string(allow_none=True),
    },
)


class StandupInput(ApiSchema):
    name = fields.String()
    channel_id = fields.String()
    schedule_time = fields.String()
    schedule_tz = fields.String()
    schedule_days = fields.List(
        fields.String(validate=validate.OneOf(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]))
    )
    questions = fields.List(fields.String())
    participants = fields.List(fields.String())
    active = fields.Boolean()
    reminder_minutes = fields.Integer(validate=validate.Range(min=-1))
    report_channel = fields.String()
    report_time = fields.String()
    digest_email = fields.String()
    digest_enabled = fields.Boolean()
    nudge_missing = fields.Boolean()
    nudge_minutes_before = fields.Integer(validate=validate.Range(min=1))
    group_by = fields.String()
    edit_window = fields.String(validate=validate.OneOf(["report", "4h", "none"]))
    post_to_thread = fields.Boolean()
    notify_on_report = fields.Boolean()
    post_summary = fields.Boolean()
    sync_with_channel = fields.Boolean()
    ai_summary_enabled = fields.Boolean()
    ai_provider = fields.String(validate=validate.OneOf(["openai", "anthropic"]))
    jira_base_url = fields.String()
    github_repo = fields.String()
    linear_team = fields.String()
    manager_email = fields.String()
    manager_digest_enabled = fields.Boolean()
    feed_token = fields.String()
    feed_public = fields.Boolean()


ScheduleParticipation = model(
    "ScheduleParticipation",
    schedule_id=integer(),
    name=string(),
    occurrence_days=integer(),
    participants=integer(),
    expected=integer(),
    completed=integer(),
    missed=integer(),
    completion_rate=integer(),
    series=fields.List(fields.Integer(allow_none=True), required=True),
)
ParticipationDay = model(
    "ParticipationDay", date=iso("date"), expected=integer(), completed=integer(), blocked=boolean()
)
ParticipationSummary = model(
    "ParticipationSummary",
    **{
        key: integer()
        for key in (
            "days",
            "completion_rate",
            "expected",
            "completed",
            "missed",
            "responses",
            "total_members",
            "enrolled_members",
            "unenrolled_members",
            "on_vacation_members",
            "responding_members",
        )
    },
)
ParticipationMember = model(
    "ParticipationMember",
    user_id=string(),
    real_name=string(allow_none=True),
    enrolled=boolean(),
    on_vacation=boolean(),
    expected=integer(),
    completed=integer(),
    missed=integer(),
    responses=integer(),
    completion_rate=integer(),
    last_standup=iso(allow_none=True),
    days_with_blockers=integer(),
    days=nested(ParticipationDay, many=True),
    schedules=strings(),
    schedule_ids=fields.List(fields.Integer(), required=True),
)
ReportParticipation = model(
    "ReportParticipation",
    user_id=string(),
    name=string(),
    responses=integer(),
    completed=integer(),
    expected=integer(),
    total=integer(),
    enrolled=boolean(),
    on_vacation=boolean(),
    schedules=strings(),
    completion_rate=integer(),
    stars=integer(),
)
StandupResponse = model(
    "StandupResponse",
    id=fields.Integer(),
    team_id=fields.String(),
    user_id=string(),
    user_name=fields.String(allow_none=True),
    real_name=fields.String(allow_none=True),
    standup_date=iso("date"),
    yesterday=string(allow_none=True),
    today=string(allow_none=True),
    blockers=string(allow_none=True),
    has_blockers=boolean(),
    submitted_at=iso(allow_none=True),
    mood=string(allow_none=True),
    schedule_id=integer(allow_none=True),
    questions=fields.List(fields.String(), allow_none=True),
)
Reports = model(
    "ReportsData",
    standups=nested(StandupResponse, many=True),
    channel_names=fields.Dict(keys=fields.String(), values=fields.String(), required=True, dump_default=dict),
    participation=nested(ReportParticipation, many=True),
    total_days=integer(),
    summary=nested(ParticipationSummary),
    schedules=nested(ScheduleParticipation, many=True),
)
Stats = model(
    "Stats",
    schedules=nested(ScheduleParticipation, many=True),
    **{
        key: integer()
        for key in (
            "completion_rate",
            "active_members",
            "total_responses",
            "responses_this_week",
            "total_members",
            "enrolled_members",
            "unenrolled_members",
            "on_vacation_members",
            "expected_responses",
            "completed_responses",
            "missed_responses",
            "days",
        )
    },
)
Analytics = model(
    "AnalyticsData",
    members=nested(ParticipationMember, many=True),
    schedules=nested(ScheduleParticipation, many=True),
    window_days=strings(),
    **{
        key: integer()
        for key in (
            "days",
            "expected",
            "completed",
            "missed",
            "completion_rate",
            "enrolled_members",
            "unenrolled_members",
            "on_vacation_members",
        )
    },
)
StandupTemplate = model(
    "StandupTemplate", id=string(), name=string(), icon=string(), description=string(), questions=strings()
)
Rule = model(
    "AutomationRule",
    id=integer(),
    team_id=string(),
    name=string(),
    trigger=string(),
    condition_value=string(allow_none=True),
    action=string(),
    action_target=string(),
    action_message=string(allow_none=True),
    active=boolean(),
    created_at=iso(),
)
RuleInput = model(
    "AutomationRuleInput",
    name=string(),
    trigger=string(),
    condition_value=fields.String(allow_none=True),
    action=string(),
    action_target=string(),
    action_message=fields.String(allow_none=True),
)
Webhook = model(
    "Webhook",
    id=integer(),
    url=string(),
    webhook_url=string(),
    events=strings(),
    has_secret=boolean(),
    secret_prefix=string(allow_none=True),
    signed=boolean(),
    created_at=iso(allow_none=True),
    secret=fields.String(),
    secret_shown_once=fields.Boolean(),
)
WebhookInput = model("WebhookInput", url=fields.String(), events=fields.List(fields.String()))
WebhookEvents = model("WebhookEvents", events=strings(), default=strings())
WebhookDelivery = model(
    "WebhookDelivery",
    id=integer(),
    webhook_id=integer(),
    event_type=string(),
    status_code=integer(allow_none=True),
    ok=boolean(),
    signed=boolean(),
    error=string(allow_none=True),
    duration_ms=integer(),
    created_at=iso(),
)
WebhookTest = model(
    "WebhookTest",
    webhook_id=integer(),
    event=string(),
    status_code=integer(allow_none=True),
    ok=boolean(),
    signed=boolean(),
    error=string(allow_none=True),
    duration_ms=integer(),
)
FeedToken = model("FeedToken", token=string(), url=string())
McpKey = model(
    "McpKey",
    id=integer(),
    key_prefix=string(),
    name=string(),
    created_at=iso(),
    last_used_at=iso(allow_none=True),
    active=boolean(),
)
McpKeys = model("McpKeys", keys=nested(McpKey, many=True))
McpKeyCreated = model("McpKeyCreated", key=string(), message=string())
PublicFeedResponse = model(
    "PublicFeedResponse",
    user_id=string(),
    user_name=string(allow_none=True),
    yesterday=string(allow_none=True),
    today=string(allow_none=True),
    blockers=string(allow_none=True),
    has_blockers=boolean(),
    submitted_at=iso(allow_none=True),
)
PublicFeed = model("PublicFeed", title=string(), date=iso("date"), standups=nested(PublicFeedResponse, many=True))

RoleInput = model("RoleInput", role=fields.String(load_default="member", validate=validate.OneOf(["admin", "member"])))
InviteMemberInput = model(
    "InviteMemberInput",
    user_id=string(),
    role=fields.String(load_default="admin", validate=validate.OneOf(["admin", "member"])),
)
ModuleInput = model("ModuleInput", enabled=boolean())
McpKeyInput = model("McpKeyInput", name=fields.String(load_default="Default"))
MemberQuery = model("MemberQuery", channel_id=fields.String())
DaysQuery = model("DaysQuery", days=fields.Integer(validate=validate.Range(min=1, max=365)))
LimitQuery = model("LimitQuery", limit=fields.Integer(validate=validate.Range(min=1, max=200)))
ReportQuery = model("ReportQuery", date_from=fields.String(), date_to=fields.String(), user_id=fields.String())
ExportQuery = model("ExportQuery", **{"from": fields.String(), "to": fields.String()})


# ── Member profile ──────────────────────────────────────────────────────────

# Caps on the free-text fields, shared by the dashboard, the Slack modal and
# the database CHECK constraints in 051_member_profiles.sql.
PROFILE_TEXT_LIMITS = {"role": 80, "location": 80, "ask_me_about": 200}

# 2000 was a leap year, so 29 February passes and 30 February does not.
_LEAP_YEAR = 2000


class MemberProfile(ApiSchema):
    """The one validation every profile write goes through.

    The dashboard, the Slack modal and the CSV import all call
    db.upsert_member_profile, which loads the fields through this schema, so
    no entry point can store what another would refuse. There is no year
    field: an unknown key such as `birth_year` is dropped, never stored.
    """

    birth_month = fields.Integer(allow_none=True, validate=validate.Range(min=1, max=12))
    birth_day = fields.Integer(allow_none=True, validate=validate.Range(min=1, max=31))
    start_date = fields.Date(allow_none=True)
    role = fields.String(allow_none=True, validate=validate.Length(max=PROFILE_TEXT_LIMITS["role"]))
    location = fields.String(allow_none=True, validate=validate.Length(max=PROFILE_TEXT_LIMITS["location"]))
    ask_me_about = fields.String(allow_none=True, validate=validate.Length(max=PROFILE_TEXT_LIMITS["ask_me_about"]))
    celebrate = fields.Boolean()

    @pre_load
    def _blank_is_none(self, data, **kwargs):
        """Trim text, and treat an emptied field as cleared rather than as ''."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key in ("role", "location", "ask_me_about", "start_date", "birth_month", "birth_day"):
            value = out.get(key)
            if isinstance(value, str):
                out[key] = value.strip() or None
        return out

    @validates_schema
    def _birthday_is_a_real_day(self, data, **kwargs):
        # Written as a pair so a partial update can never leave half a birthday.
        if ("birth_month" in data) != ("birth_day" in data):
            raise ValidationError("Send the birthday month and day together.", "birth_day")
        month, day = data.get("birth_month"), data.get("birth_day")
        if (month is None) != (day is None):
            raise ValidationError("Choose both a month and a day, or neither.", "birth_day")
        if month is None:
            return
        try:
            date(_LEAP_YEAR, month, day)
        except ValueError:
            raise ValidationError("That day does not exist in that month.", "birth_day") from None

    @validates_schema
    def _start_date_is_plausible(self, data, **kwargs):
        start = data.get("start_date")
        if start is None:
            return
        # A start date a few months ahead is normal for a new hire, so the
        # future is allowed, up to a year.
        if start.year < 1900 or start > datetime.now(timezone.utc).date() + timedelta(days=366):
            raise ValidationError("Enter a start date after 1900 and no more than a year ahead.", "start_date")


MemberProfileRecord = model(
    "MemberProfileRecord",
    user_id=string(),
    birth_month=integer(allow_none=True),
    birth_day=integer(allow_none=True),
    start_date=iso("date", allow_none=True),
    role=string(allow_none=True),
    location=string(allow_none=True),
    ask_me_about=string(allow_none=True),
    celebrate=boolean(),
    updated_by=string(allow_none=True),
    updated_at=iso(allow_none=True),
    # True when someone other than the person wrote the row last, so the page
    # can say "set by an admin" and the person knows to check it.
    set_by_admin=boolean(),
    left_at=iso(allow_none=True),
)
ProfileImportInput = model(
    "ProfileImportInput",
    csv=fields.String(required=True, validate=validate.Length(min=1, max=1_000_000)),
    # Preview is the default so a request that forgets the flag writes nothing.
    preview=fields.Boolean(load_default=True),
    overwrite=fields.Boolean(load_default=False),
)
ProfileImportRow = model(
    "ProfileImportRow",
    line=integer(),
    email=string(),
    user_id=string(allow_none=True),
    status=string(validate=validate.OneOf(["ready", "unchanged", "kept", "unmatched", "invalid"])),
    birth_month=integer(allow_none=True),
    birth_day=integer(allow_none=True),
    start_date=iso("date", allow_none=True),
    error=string(allow_none=True),
)
ProfileImportResult = model(
    "ProfileImportResult",
    preview=boolean(),
    overwrite=boolean(),
    **{key: integer() for key in ("rows_read", "ready", "written", "unchanged", "kept", "unmatched", "invalid")},
    rows=nested(ProfileImportRow, many=True),
)
