"""Cross-feature insights and today view contracts."""

from marshmallow import fields, validate

from src.core.api_schemas import StandupResponse, boolean, integer, iso, model, nested, string
from src.modules.kudos.schemas import Kudos

Unrecognised = model(
    "UnrecognisedContributor",
    user_id=string(),
    real_name=string(allow_none=True),
    standups=integer(),
    last_standup=iso("date", allow_none=True),
    kudos=integer(),
)
Stuck = model(
    "PersistentBlocker",
    user_id=string(),
    real_name=string(allow_none=True),
    days=integer(),
    first_seen=iso("date"),
    last_seen=iso("date"),
    text=string(),
)
Insights = model(
    "InsightsData", window_days=integer(), unrecognised=nested(Unrecognised, many=True), stuck=nested(Stuck, many=True)
)
Awaiting = model("AwaitingResponse", user_id=string(), real_name=string(allow_none=True))
Blocked = model(
    "BlockedResponse",
    user_id=string(),
    real_name=string(allow_none=True),
    blockers=string(),
    submitted_at=iso(allow_none=True),
)
NextChat = model(
    "NextChat", program_id=integer(), name=string(), date=iso("date"), days_away=integer(), overdue=boolean()
)
Counts = model("TodayCounts", expected=integer(), answered=integer(), awaiting=integer(), blocked=integer())
Today = model(
    "Today",
    date=iso("date"),
    counts=nested(Counts),
    responses=nested(StandupResponse, many=True),
    awaiting=nested(Awaiting, many=True),
    blocked=nested(Blocked, many=True),
    kudos=nested(Kudos, many=True),
    next_chat=nested(NextChat, allow_none=True),
)
InsightsQuery = model(
    "InsightsQuery",
    days=fields.Integer(validate=validate.Range(min=7, max=90)),
    min_blocker_days=fields.Integer(validate=validate.Range(min=2, max=10)),
)
TodayQuery = model("TodayQuery", kudos=fields.Integer(validate=validate.Range(min=1, max=20)))
