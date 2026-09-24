"""Connect browser API schemas."""

from marshmallow import fields, validate

from src.core.api_schemas import ApiSchema, boolean, integer, iso, model, string, strings

Program = model(
    "ConnectProgram",
    id=integer(),
    team_id=string(),
    name=string(),
    channel_id=string(),
    interval_weeks=integer(),
    day_of_week=integer(),
    hour=integer(),
    minute=integer(),
    timezone=string(),
    enabled=boolean(),
    created_at=iso(allow_none=True),
    match_working_hours=boolean(),
    meeting_minutes=integer(),
    meeting_link=string(allow_none=True),
    suggest_times=boolean(),
    use_icebreaker=boolean(),
    post_stats=boolean(),
    group_size=integer(),
    strict_group_size=boolean(),
    intro_tone=string(),
    video_mode=string(),
    next_round_date=iso("date", allow_none=True),
    upcoming_round=iso("date", allow_none=True, required=False),
    round_count=fields.Integer(),
    last_round=iso(allow_none=True, required=False),
    pool_size=fields.Integer(allow_none=True),
)


class ProgramInput(ApiSchema):
    name = fields.String()
    channel_id = fields.String()
    interval_weeks = fields.Integer(validate=validate.Range(min=1, max=8))
    day_of_week = fields.Integer(validate=validate.Range(min=0, max=6))
    hour = fields.Integer(validate=validate.Range(min=0, max=23))
    minute = fields.Integer(validate=validate.Range(min=0, max=59))
    timezone = fields.String()
    enabled = fields.Boolean()
    match_working_hours = fields.Boolean()
    meeting_minutes = fields.Integer(validate=validate.OneOf([15, 30, 45, 60]))
    meeting_link = fields.String(allow_none=True, validate=validate.Regexp(r"^(?:https?://.*)?$"))
    suggest_times = fields.Boolean()
    use_icebreaker = fields.Boolean()
    post_stats = fields.Boolean()
    group_size = fields.Integer(validate=validate.Range(min=2, max=8))
    strict_group_size = fields.Boolean()
    intro_tone = fields.String(validate=validate.OneOf(["hybrid", "remote", "in_person"]))
    video_mode = fields.String(validate=validate.OneOf(["link", "zoom", "none"]))
    next_round_date = fields.Date(allow_none=True)


Round = model(
    "ConnectRound",
    id=integer(),
    program_id=integer(),
    team_id=string(),
    scheduled_for=iso(),
    state=string(),
    member_count=integer(),
    created_at=iso(allow_none=True),
    **{
        key: integer()
        for key in ("matches", "met", "missed", "no_reply", "undelivered", "agreed", "with_zoom", "rematch_requests")
    },
)
Match = model(
    "ConnectMatch",
    id=integer(),
    members=strings(),
    status=string(),
    delivered_at=iso(allow_none=True),
    nudged_at=iso(allow_none=True),
    agreed_at=iso(allow_none=True),
    has_zoom=boolean(),
)
ProgramMember = model(
    "ConnectMember",
    user_id=string(),
    name=string(),
    avatar=string(),
    eligible=boolean(),
    state=string(),
    until=iso("date", allow_none=True),
    paired=integer(),
)
MemberState = model("ConnectMemberState", user_id=string(), state=string(), until=iso("date", allow_none=True))
MemberInput = model(
    "ConnectMemberInput",
    state=fields.String(required=True, validate=validate.OneOf(["in", "out", "snoozed"])),
    weeks=fields.Integer(validate=validate.Range(min=1, max=52)),
)
Participation = model(
    "ConnectParticipation",
    user_id=string(),
    paired=integer(),
    met=integer(),
    missed=integer(),
    no_reply=integer(),
    last_met=iso(allow_none=True),
)
ZoomSummary = model("ZoomSummary", configured=boolean(), linked=integer(), needs_reconnect=integer())
RunStarted = model("ConnectRunStarted", started=boolean(), round=integer(allow_none=True))
DeletedProgram = model("DeletedProgram", deleted=integer())
RoundsQuery = model("RoundsQuery", rounds=fields.Integer(validate=validate.Range(min=1, max=52)))
