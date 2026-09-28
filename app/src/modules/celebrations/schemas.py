"""Celebrations browser API schemas."""

from marshmallow import fields, validate

from src.core.api_schemas import ApiSchema, boolean, integer, iso, model, nested, string, strings
from src.core.workspace_calendar import MAX_HOLIDAY_NAME, WEEKDAY_KEYS

Settings = model(
    "CelebrationSettings",
    channel_id=string(allow_none=True),
    timezone=string(allow_none=True),
    post_time=string(),
    birthdays=boolean(),
    anniversaries=boolean(),
    # From the core workspace calendar, edited here in this release.
    working_days=strings(),
    # A channel and a timezone are set, so posts can go out once enabled.
    ready=boolean(),
    # Whether the installation granted reactions:write, so the page can say
    # the 🎉 needs a reinstall.
    can_react=boolean(),
    updated_at=iso(allow_none=True),
)


class SettingsInput(ApiSchema):
    channel_id = fields.String(required=True, validate=validate.Length(min=1, max=40))
    timezone = fields.String(required=True, validate=validate.Length(min=1, max=64))
    post_time = fields.String(load_default="09:00", validate=validate.Regexp(r"^([01][0-9]|2[0-3]):[0-5][0-9]$"))
    birthdays = fields.Boolean(load_default=True)
    anniversaries = fields.Boolean(load_default=True)
    working_days = fields.List(
        fields.String(validate=validate.OneOf(WEEKDAY_KEYS)),
        required=True,
        validate=validate.Length(min=1, max=7),
    )


Holiday = model("Holiday", date=iso("date"), name=string())


class HolidayInput(ApiSchema):
    date = fields.Date(required=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=MAX_HOLIDAY_NAME))


HolidayImportInput = model(
    "HolidayImportInput",
    csv=fields.String(required=True, validate=validate.Length(min=1, max=200_000)),
    # Preview is the default so a request that forgets the flag writes nothing.
    preview=fields.Boolean(load_default=True),
)
HolidayImportRow = model(
    "HolidayImportRow",
    line=integer(),
    date=iso("date", allow_none=True),
    name=string(),
    status=string(validate=validate.OneOf(["ready", "invalid"])),
    error=string(allow_none=True),
)
HolidayImportResult = model(
    "HolidayImportResult",
    preview=boolean(),
    ready=integer(),
    invalid=integer(),
    written=integer(),
    rows=nested(HolidayImportRow, many=True),
)

Upcoming = model(
    "UpcomingCelebration",
    kind=string(validate=validate.OneOf(["birthday", "anniversary"])),
    date=iso("date"),
    posted_on=iso("date"),
    user_id=string(),
    years=integer(allow_none=True),
)

AskPreview = model(
    "AskForDatesPreview",
    count=integer(),
    message=string(),
    ready=boolean(),
)
AskResult = model("AskForDatesResult", count=integer())
