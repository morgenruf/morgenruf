"""Pulse browser API schemas."""

from marshmallow import fields, validate

from src.core.api_schemas import boolean, integer, iso, model

Settings = model(
    "PulseSettings",
    enabled=boolean(),
    # 0 is Monday, as the scheduler counts.
    day_of_week=integer(),
    hour=integer(),
    minute=integer(),
    timezone=fields.String(required=True),
    # Null asks every active member.
    audience_channel_id=fields.String(required=True, allow_none=True),
    updated_at=iso(allow_none=True),
)
SettingsInput = model(
    "PulseSettingsInput",
    enabled=fields.Boolean(required=True),
    day_of_week=fields.Integer(required=True, validate=validate.Range(min=0, max=6)),
    hour=fields.Integer(required=True, validate=validate.Range(min=0, max=23)),
    minute=fields.Integer(required=True, validate=validate.Range(min=0, max=59)),
    timezone=fields.String(required=True, validate=validate.Length(min=1, max=64)),
    # Empty asks every active member.
    audience_channel_id=fields.String(
        load_default="",
        allow_none=True,
        validate=validate.Length(max=40),
    ),
)
# An open round, or one under five people, carries only sent_on, respondents,
# invited, hidden, needed (and open). The result fields are absent, not null.
# Under ten, mood_dist and enps are absent too.
Round = model(
    "PulseRound",
    sent_on=iso("date"),
    respondents=integer(),
    invited=integer(),
    hidden=boolean(),
    needed=fields.Integer(),
    # True while the round is still open: no results until it closes.
    open=fields.Boolean(),
    includes_enps=fields.Boolean(),
    mood_avg=fields.Float(allow_none=True),
    mood_dist=fields.List(fields.Integer(), allow_none=True),
    enps=fields.Integer(allow_none=True),
)
