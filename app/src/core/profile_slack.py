"""The member profile in Slack: the modal, the App Home section, /morgenruf.

The same modal opens from the App Home "Edit" button and from
`/morgenruf profile`, and both save through db.upsert_member_profile, which is
also what the dashboard uses. There is one validation for all of them.

`/morgenruf` lives in core because it is the product's command, not any one
feature's: later features add subcommands here rather than each asking every
workspace to update the Slack app for a command of their own.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from src.core.profile import MONTHS, birthday_label, is_empty, joined_label

logger = logging.getLogger(__name__)

MODAL_CALLBACK = "profile:modal"
EDIT_ACTION = "profile:edit"

# Block ids double as the field names, so a validation error for a field can
# be shown on the block that holds it.
_TEXT_FIELDS = (
    ("role", "Role", "e.g. Backend engineer", False, 80),
    ("location", "Location", "e.g. Berlin", False, 80),
    ("ask_me_about", "Ask me about", "e.g. Rust, bouldering, sourdough", True, 200),
)

_NOT_SET = "0"

_EMPTY_HINT = "Add your birthday and start date so the team can celebrate with you."


def _escape(text: str) -> str:
    """Keep what a person typed as text, so `<!channel>` cannot ping anyone."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _option(text: str, value: str) -> dict:
    return {"text": {"type": "plain_text", "text": text}, "value": value}


# ── App Home ────────────────────────────────────────────────────────────────


def home_blocks(team_id: str, user_id: str) -> list[dict]:
    """The "Your profile" section of the App Home, with an Edit button."""
    import src.core.db as db  # noqa: PLC0415

    try:
        row = db.get_member_profile(team_id, user_id)
    except Exception as exc:
        logger.warning("profile App Home unavailable for %s: %s", team_id, exc)
        return []

    edit = {
        "type": "button",
        "action_id": EDIT_ACTION,
        "text": {"type": "plain_text", "text": "Edit", "emoji": True},
        "value": "home",
    }
    if is_empty(row):
        return [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Your profile*\n{_EMPTY_HINT}"},
                "accessory": edit,
            },
        ]

    blocks: list[dict] = [
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Your profile*"}, "accessory": edit},
    ]
    facts = []
    if row.get("role"):
        facts.append(f"💼 {_escape(row['role'])}")
    birthday = birthday_label(row.get("birth_month"), row.get("birth_day"))
    if birthday:
        facts.append(f"🎂 {birthday}")
    joined = joined_label(row.get("start_date"))
    if joined:
        facts.append(f"🗓️ {joined}")
    if row.get("location"):
        facts.append(f"📍 {_escape(row['location'])}")
    if facts:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "   ".join(facts)}]})
    if row.get("ask_me_about"):
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Ask me about: {_escape(row['ask_me_about'])}"}],
            }
        )
    notes = []
    if not row.get("celebrate", True):
        notes.append("You asked not to be celebrated publicly.")
    if row.get("updated_by") and row.get("updated_by") != user_id:
        notes.append("Last changed by an admin. Edit it if anything is wrong.")
    if notes:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " ".join(notes)}]})
    return blocks


# ── Modal ───────────────────────────────────────────────────────────────────


def profile_modal(row: dict | None, source: str = "home") -> dict:
    """The profile form, filled in with what is stored."""
    row = row or {}
    month = row.get("birth_month")
    day = row.get("birth_day")
    start = row.get("start_date")

    month_options = [_option("Not set", _NOT_SET)] + [_option(name, str(i)) for i, name in enumerate(MONTHS, 1)]
    day_options = [_option("Not set", _NOT_SET)] + [_option(str(d), str(d)) for d in range(1, 32)]

    month_select: dict = {
        "type": "static_select",
        "action_id": "profile:birth_month",
        "placeholder": {"type": "plain_text", "text": "Month"},
        "options": month_options,
    }
    if month:
        month_select["initial_option"] = month_options[month]
    day_select: dict = {
        "type": "static_select",
        "action_id": "profile:birth_day",
        "placeholder": {"type": "plain_text", "text": "Day"},
        "options": day_options,
    }
    if day:
        day_select["initial_option"] = day_options[day]
    start_picker: dict = {
        "type": "datepicker",
        "action_id": "profile:start_date",
        "placeholder": {"type": "plain_text", "text": "Pick a date"},
    }
    if start:
        start_picker["initial_date"] = start.isoformat() if hasattr(start, "isoformat") else str(start)

    blocks: list[dict] = [
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Only the day and month of your birthday are kept, never the year.",
                }
            ],
        },
        {
            "type": "input",
            "block_id": "birth_month",
            "optional": True,
            "label": {"type": "plain_text", "text": "Birthday month"},
            "element": month_select,
        },
        {
            "type": "input",
            "block_id": "birth_day",
            "optional": True,
            "label": {"type": "plain_text", "text": "Birthday day"},
            "element": day_select,
        },
        {
            "type": "input",
            "block_id": "start_date",
            "optional": True,
            "label": {"type": "plain_text", "text": "Started on"},
            "element": start_picker,
        },
    ]

    for field, label, placeholder, multiline, limit in _TEXT_FIELDS:
        element: dict = {
            "type": "plain_text_input",
            "action_id": f"profile:{field}",
            "max_length": limit,
            "multiline": multiline,
            "placeholder": {"type": "plain_text", "text": placeholder},
        }
        if row.get(field):
            element["initial_value"] = row[field]
        blocks.append(
            {
                "type": "input",
                "block_id": field,
                "optional": True,
                "label": {"type": "plain_text", "text": label},
                "element": element,
            }
        )

    no_celebrate = _option("Don't celebrate me publicly", "no_celebrate")
    options = [no_celebrate]
    # A datepicker cannot be emptied once it holds a date, so clearing the
    # start date needs a control of its own.
    if start:
        options.append(_option("Remove my start date", "clear_start"))
    checkboxes: dict = {"type": "checkboxes", "action_id": "profile:options", "options": options}
    if not row.get("celebrate", True):
        checkboxes["initial_options"] = [no_celebrate]
    blocks.append(
        {
            "type": "input",
            "block_id": "options",
            "optional": True,
            "label": {"type": "plain_text", "text": "Options"},
            "element": checkboxes,
        }
    )

    return {
        "type": "modal",
        "callback_id": MODAL_CALLBACK,
        "private_metadata": json.dumps({"source": source}),
        "title": {"type": "plain_text", "text": "Your profile"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def fields_from_submission(values: dict) -> dict:
    """Turn the modal's state into profile fields, before validation."""

    def state(block: str) -> dict:
        return (values.get(block) or {}).get(f"profile:{block}") or {}

    def selected(block: str):
        option = state(block).get("selected_option") or {}
        value = option.get("value")
        return None if value in (None, _NOT_SET) else int(value)

    chosen = {o.get("value") for o in (state("options").get("selected_options") or [])}
    start = state("start_date").get("selected_date")
    fields = {
        "birth_month": selected("birth_month"),
        "birth_day": selected("birth_day"),
        "start_date": None if "clear_start" in chosen else (start or None),
        "celebrate": "no_celebrate" not in chosen,
    }
    for field, *_ in _TEXT_FIELDS:
        fields[field] = state(field).get("value")
    return fields


def modal_errors(messages: dict) -> dict:
    """Schema errors keyed by the modal block that should show them."""
    blocks = {"birth_month", "birth_day", "start_date", "role", "location", "ask_me_about"}
    out: dict[str, str] = {}
    for field, reasons in (messages or {}).items():
        text = " ".join(reasons) if isinstance(reasons, list) else str(reasons)
        out[field if field in blocks else "birth_day"] = text
    return out


def saved_view(row: dict) -> dict:
    """What the modal turns into after saving, so the person sees it took."""
    lines = []
    birthday = birthday_label(row.get("birth_month"), row.get("birth_day"))
    lines.append(f"🎂 Birthday: {birthday or 'not set'}")
    start = row.get("start_date")
    lines.append(f"🗓️ Started: {start.strftime('%-d %B %Y') if isinstance(start, date) else 'not set'}")
    for field, label, *_ in _TEXT_FIELDS:
        if row.get(field):
            lines.append(f"{label}: {_escape(row[field])}")
    if not row.get("celebrate", True):
        lines.append("You will not be celebrated publicly.")
    return {
        "type": "modal",
        "callback_id": "profile:saved",
        "title": {"type": "plain_text", "text": "Your profile"},
        "close": {"type": "plain_text", "text": "Done"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Saved.*\n" + "\n".join(lines)}},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Change it any time with `/morgenruf profile` or from the Morgenruf dashboard.",
                    }
                ],
            },
        ],
    }


def save_submission(team_id: str, user_id: str, values: dict) -> tuple[dict | None, dict]:
    """Validate and store a modal submission. Returns (row, errors by block)."""
    import src.core.db as db  # noqa: PLC0415

    fields = fields_from_submission(values)
    try:
        row = db.upsert_member_profile(team_id, user_id, fields, updated_by=user_id)
    except ValueError as exc:
        return None, modal_errors(getattr(exc, "messages", None) or {"birth_day": [str(exc)]})
    return row, {}


# ── /morgenruf ──────────────────────────────────────────────────────────────


def help_blocks(team_id: str, prefix: str = "") -> list[dict]:
    """What Morgenruf can do in this workspace, from the modules it has on."""
    lines = [
        "*Your profile*",
        "• `/morgenruf profile`: your birthday, start date, role and location",
    ]
    try:
        import src.core.db as db  # noqa: PLC0415
        from src.core.modules import active_modules, deploy_allowlist  # noqa: PLC0415
        from src.modules import REGISTRY  # noqa: PLC0415

        mods = active_modules(
            REGISTRY,
            granted_scopes=db.granted_scopes(team_id),
            settings=db.module_settings(team_id),
            allowlist=deploy_allowlist(),
        )
    except Exception as exc:
        logger.warning("help could not resolve modules for %s: %s", team_id, exc)
        mods = []
    for spec in mods:
        help_lines = getattr(spec, "help_lines", ())
        if not help_lines:
            continue
        label = spec.nav[0].label if spec.nav else spec.name
        lines.append("")
        lines.append(f"*{label}*")
        lines.extend(f"• {line}" for line in help_lines)
    lines += [
        "",
        "*Anywhere*",
        "• `/morgenruf help`: show this message",
        "• The *Home* tab shows your standups, your profile and more",
        "",
        "📖 Full docs: <https://docs.morgenruf.dev|docs.morgenruf.dev>",
    ]
    text = "\n".join(lines)
    if prefix:
        text = f"{prefix}\n\n{text}"
    return [
        {"type": "header", "text": {"type": "plain_text", "text": "🌅 Morgenruf commands", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]


def open_profile_modal(client, trigger_id: str, team_id: str, user_id: str, source: str) -> None:
    import src.core.db as db  # noqa: PLC0415

    try:
        row = db.get_member_profile(team_id, user_id)
    except Exception as exc:
        logger.warning("profile: could not load %s in %s: %s", user_id, team_id, exc)
        row = None
    client.views_open(trigger_id=trigger_id, view=profile_modal(row, source=source))


def register_slack(app) -> None:
    """Attach /morgenruf and the profile modal to the Bolt app."""

    @app.command("/morgenruf")
    def handle_morgenruf_command(ack, body, client):  # noqa: ANN001
        """`/morgenruf profile` opens the modal. Anything else, or nothing, is help."""
        ack()
        user_id = body.get("user_id", "")
        team_id = body.get("team_id", "")
        words = (body.get("text") or "").strip().split()
        sub = words[0].lower() if words else ""

        if sub == "profile":
            try:
                open_profile_modal(client, body.get("trigger_id", ""), team_id, user_id, source="command")
            except Exception:
                logger.exception("profile: could not open the modal for %s", user_id)
            return

        prefix = "" if sub in ("", "help") else f"I don't know `{_escape(sub)}`. Here is what I can do:"
        try:
            client.chat_postMessage(channel=user_id, text="Morgenruf help", blocks=help_blocks(team_id, prefix))
        except Exception:
            logger.exception("could not send /morgenruf help to %s", user_id)

    @app.action(EDIT_ACTION)
    def handle_edit_profile(ack, body, client):  # noqa: ANN001
        ack()
        user_id = body["user"]["id"]
        team_id = (body.get("team") or {}).get("id") or body["user"].get("team_id", "")
        try:
            open_profile_modal(client, body.get("trigger_id", ""), team_id, user_id, source="home")
        except Exception:
            logger.exception("profile: could not open the modal for %s", user_id)

    @app.view(MODAL_CALLBACK)
    def handle_profile_submit(ack, body, view):  # noqa: ANN001
        user_id = body["user"]["id"]
        team_id = (body.get("team") or {}).get("id") or body["user"].get("team_id", "")
        values = (view or {}).get("state", {}).get("values", {})
        try:
            row, errors = save_submission(team_id, user_id, values)
        except Exception:
            logger.exception("profile: could not save %s in %s", user_id, team_id)
            ack(response_action="errors", errors={"birth_month": "Could not save just now. Try again in a minute."})
            return
        if errors:
            ack(response_action="errors", errors=errors)
            return
        ack(response_action="update", view=saved_view(row or {}))
