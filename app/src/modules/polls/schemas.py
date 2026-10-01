"""Polls browser API schemas."""

from marshmallow import fields

from src.core.api_schemas import boolean, integer, iso, model, nested, string

PollOption = model(
    "PollOption",
    text=string(),
    # Null while the poll hides its results and is still open.
    votes=fields.Integer(required=True, allow_none=True),
    # Who picked it, on a named poll whose results are showing. Null otherwise,
    # and always null on an anonymous poll.
    voters=fields.List(fields.String(), required=True, allow_none=True),
)
Poll = model(
    "Poll",
    id=integer(),
    question=string(),
    channel_id=string(),
    created_by=string(),
    anonymous=boolean(),
    multiple=boolean(),
    hide_results=boolean(),
    created_at=iso(),
    closes_at=iso(allow_none=True),
    closed_at=iso(allow_none=True),
    total_votes=integer(),
    can_close=boolean(),
    options=nested(PollOption, many=True),
)
