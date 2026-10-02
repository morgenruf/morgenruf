"""Watercooler browser API schemas."""

from marshmallow import fields, validate

from src.core.api_schemas import ApiSchema, boolean, integer, model, nested, string, strings
from src.modules.watercooler.bank import CATEGORIES

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

Channel = model(
    "WatercoolerChannel",
    channel_id=string(),
    days=strings(),
    post_time=string(),
    timezone=string(),
    source=string(validate=validate.OneOf(["builtin", "custom", "both"])),
    categories=strings(),
    active=boolean(),
    # Why it stopped on its own (not_in_channel, empty_pool), or null.
    paused_reason=string(allow_none=True),
)

Question = model("WatercoolerQuestion", id=integer(), text=string(), archived=boolean())

BankQuestion = model("WatercoolerBankQuestion", key=string(), category=string(), text=string(), hidden=boolean())

Category = model("WatercoolerCategory", key=string(), label=string())

Overview = model(
    "WatercoolerOverview",
    channels=nested(Channel, many=True),
    questions=nested(Question, many=True),
    bank=nested(BankQuestion, many=True),
    categories=nested(Category, many=True),
    # Whether the viewer may change anything here.
    can_manage=boolean(),
    max_channels=integer(),
    max_questions=integer(),
)

PostResult = model("WatercoolerPostResult", posted=boolean())


class WatercoolerChannelInput(ApiSchema):
    days = fields.List(
        fields.String(validate=validate.OneOf(_WEEKDAYS)), required=True, validate=validate.Length(min=1, max=7)
    )
    post_time = fields.String(required=True, validate=validate.Regexp(r"^([01][0-9]|2[0-3]):[0-5][0-9]$"))
    timezone = fields.String(required=True, validate=validate.Length(min=1, max=64))
    source = fields.String(load_default="both", validate=validate.OneOf(["builtin", "custom", "both"]))
    categories = fields.List(
        fields.String(validate=validate.OneOf(CATEGORIES)),
        load_default=list(CATEGORIES),
        validate=validate.Length(min=1, max=len(CATEGORIES)),
    )
    active = fields.Boolean(load_default=True)


class WatercoolerQuestionInput(ApiSchema):
    text = fields.String(required=True, validate=validate.Length(min=5, max=300))


class WatercoolerQuestionUpdate(ApiSchema):
    text = fields.String(validate=validate.Length(min=5, max=300))
    archived = fields.Boolean()


class WatercoolerHiddenInput(ApiSchema):
    hidden = fields.Boolean(required=True)
