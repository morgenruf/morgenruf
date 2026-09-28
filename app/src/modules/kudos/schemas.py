"""Recognition browser API schemas."""

from marshmallow import fields, validate

from src.core.api_schemas import boolean, integer, iso, model, string

Kudos = model(
    "KudosEntry",
    id=integer(),
    team_id=fields.String(),
    from_user=string(),
    to_user=string(),
    message=string(),
    channel_id=fields.String(allow_none=True),
    emoji=fields.String(allow_none=True),
    created_at=iso(),
    from_name=fields.String(allow_none=True),
    to_name=fields.String(allow_none=True),
)
Receiver = model("KudosReceiver", to_user=string(), received=integer(), last_kudos=iso(allow_none=True))
Giver = model("KudosGiver", user_id=string(), given=integer(), last_given=iso(allow_none=True))
Config = model(
    "KudosConfig",
    emoji=string(),
    daily_allowance=integer(),
    token_auto=boolean(),
    # Where the kudos card is shared. Empty means no kudos channel.
    channel_id=string(),
)
ConfigInput = model(
    "KudosConfigInput",
    emoji=fields.String(required=True, validate=validate.Length(min=1, max=16)),
    daily_allowance=fields.Integer(load_default=5, validate=validate.Range(min=0, max=50)),
    # Left out means leave it as it is. An empty string clears it.
    channel_id=fields.String(
        validate=validate.Regexp(r"^([CG][A-Z0-9]+)?$", error="Choose a channel from the list"),
    ),
)
