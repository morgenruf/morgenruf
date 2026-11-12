"""Personal banner cards: the person's photo, name and years, drawn per post.

An opt-in alternative to the stock banners (settings.personal_banners). The
post carries a signed URL; the app draws the card when Slack fetches it, so
nothing is stored and any pod can answer. The URL holds only what the post
already shows: the name, the years, the workspace name and the Slack photo
URL. The signature stops anyone using the route to draw cards of their own.

A card fits one person. A post for two or more people uses a stock banner.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import random
from functools import cache
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont, ImageOps

from src.modules.celebrations.rules import ANNIVERSARY, BIRTHDAY

logger = logging.getLogger(__name__)

ROUTE_PREFIX = "/celebrations/cards"
FONT_DIR = Path(__file__).parent / "fonts"
WIDTH, HEIGHT = 1200, 600
DESIGNS = {BIRTHDAY: ("deploy", "merged"), ANNIVERSARY: ("terraform", "uptime")}
ALT_TEXT = {BIRTHDAY: "A birthday card for {name}", ANNIVERSARY: "A work anniversary card for {name}"}
CACHE_SECONDS = 30 * 24 * 3600
# Only Slack's own image hosts. Anything else in a payload is ignored, so the
# route never fetches an address it was handed.
PHOTO_HOSTS = (".slack-edge.com",)
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_TIMEOUT_SECONDS = 4

ACCENT = "#1287d4"
GREEN = "#3ddc97"
RED = "#ff7a7a"


# ── Signed URLs ─────────────────────────────────────────────────────────────


def _key() -> bytes | None:
    secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    return secret.encode() if secret else None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str, key: bytes) -> str:
    return _b64(hmac.new(key, f"card:{body}".encode(), hashlib.sha256).digest()[:18])


def pick(kind: str, last: str | None, choose=random.choice) -> str:
    """A design for this kind, never the one used last time. Stored as card-<design>."""
    options = [d for d in DESIGNS[kind] if f"card-{d}" != last] or list(DESIGNS[kind])
    return choose(options)


def token(card: dict) -> str | None:
    key = _key()
    if key is None:
        return None
    body = _b64(json.dumps(card, separators=(",", ":"), ensure_ascii=False).encode())
    return f"{body}.{_sign(body, key)}"


def read_token(value: str) -> dict | None:
    """The card in a token, or None when it is malformed or not signed by this app."""
    key = _key()
    body, _, sig = (value or "").partition(".")
    if key is None or not body or not hmac.compare_digest(sig, _sign(body, key)):
        return None
    try:
        card = json.loads(_unb64(body))
    except ValueError:
        return None
    if not isinstance(card, dict) or card.get("k") not in DESIGNS or card.get("d") not in DESIGNS[card["k"]]:
        return None
    return card


def image_block(card: dict) -> dict | None:
    """The Slack image block for a card, or None when the app cannot sign or has no public URL."""
    base = (os.environ.get("APP_URL") or "").rstrip("/")
    signed = token(card)
    if not base or not signed:
        return None
    return {
        "type": "image",
        "image_url": f"{base}{ROUTE_PREFIX}/{signed}.png",
        "alt_text": ALT_TEXT[card["k"]].format(name=card.get("n") or "a teammate"),
    }


def card_for(client, user_id: str, kind: str, design: str, years: int | None, workspace: str) -> dict:
    """What a card shows, read from Slack. Falls back to no photo when Slack says nothing."""
    profile = {}
    try:
        user = (client.users_info(user=user_id) or {}).get("user") or {}
        profile = user.get("profile") or {}
        real = user.get("real_name")
    except Exception:
        logger.info("celebrations: no Slack profile for %s, card without a photo", user_id)
        real = None
    name = (profile.get("real_name") or real or profile.get("display_name") or "").strip()
    photo = "" if profile.get("is_custom_image") is False else profile.get("image_512") or ""
    card = {"k": kind, "d": design, "n": name[:60], "w": (workspace or "").strip()[:40], "a": photo}
    if kind == ANNIVERSARY:
        card["y"] = max(int(years or 1), 1)
    return card


# ── Drawing ─────────────────────────────────────────────────────────────────


@cache
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / f"{name}.ttf"), size)


def _fit(text: str, name: str, size: int, width: int, smallest: int = 20) -> ImageFont.FreeTypeFont:
    """The largest size up to `size` at which `text` fits on one line in `width`."""
    while size > smallest and _font(name, size).getlength(text) > width:
        size -= 2
    return _font(name, size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(f"{lines[-1]} {word}") <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def _text(draw, xy, text, name, size, width, fill, lines=2, smallest=24, gap=1.1, middle=False) -> int:
    """Draw `text` in at most `lines` lines inside `width`, shrinking the font as needed.

    The last line gets an ellipsis when even the smallest size does not fit.
    Returns the height drawn. With middle, `xy` is the vertical centre.
    """
    while True:
        font = _font(name, size)
        wrapped = _wrap(text, font, width)
        fits = len(wrapped) <= lines and all(font.getlength(w) <= width for w in wrapped)
        if fits or size <= smallest:
            break
        size -= 2
    wrapped = wrapped[:lines] or [""]
    if not fits:
        last = wrapped[-1]
        while last and font.getlength(f"{last}…") > width:
            last = last[:-1]
        wrapped[-1] = f"{last.rstrip()}…"
    step = int(font.size * gap)
    height = step * (len(wrapped) - 1) + font.size
    x, y = xy
    if middle:
        y -= height // 2
    for line in wrapped:
        draw.text((x, y), line, font=font, fill=fill)
        y += step
    return height


def _spaced(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill, spacing: float) -> None:
    """Letter-spaced capitals, for the small labels."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += font.getlength(char) + spacing


def _initials(name: str) -> str:
    words = [w for w in name.split() if w[:1].isalpha()]
    return "".join(w[0] for w in (words[:1] + words[1:][-1:])).upper() or "?"


def _photo(url: str) -> Image.Image | None:
    """The person's Slack photo, or None. Only Slack's image hosts are fetched."""
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(PHOTO_HOSTS):
        return None
    try:
        import requests  # noqa: PLC0415

        with requests.get(url, timeout=PHOTO_TIMEOUT_SECONDS, stream=True, allow_redirects=False) as resp:
            if resp.status_code != 200:
                return None
            data = resp.raw.read(PHOTO_MAX_BYTES + 1, decode_content=True)
        if len(data) > PHOTO_MAX_BYTES:
            return None
        image = Image.open(io.BytesIO(data))
        image.draft("RGB", (512, 512))
        return image.convert("RGB")
    except Exception:
        logger.info("celebrations: could not read a card photo, drawing initials")
        return None


def _avatar(photo: Image.Image | None, name: str, size: int, ring: str, ring_width: int, empty: str, ink: str):
    """A round photo with a ring, or the initials in the same ring. Drawn 4x and scaled for smooth edges."""
    big = size * 4
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse((0, 0, big - 1, big - 1), fill=ring)
    inner = big - ring_width * 8
    if photo is not None:
        face = ImageOps.fit(photo, (inner, inner), Image.Resampling.LANCZOS)
    else:
        face = Image.new("RGB", (inner, inner), empty)
        draw = ImageDraw.Draw(face)
        font = _font("Montserrat-ExtraBold", int(inner * 0.36))
        draw.text((inner / 2, inner / 2), _initials(name), font=font, fill=ink, anchor="mm")
    inner_mask = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(inner_mask).ellipse((0, 0, inner - 1, inner - 1), fill=255)
    out.paste(face, (ring_width * 4, ring_width * 4), inner_mask)
    out.putalpha(mask)
    return out.resize((size, size), Image.Resampling.LANCZOS)


def _first(name: str) -> str:
    return (name.split() or ["you"])[0]


def _slug(name: str) -> str:
    slug = "-".join("".join(c for c in w.lower() if c.isalnum()) for w in name.split())
    return slug.strip("-")[:24] or "teammate"


def _years(n: int) -> str:
    return "1 year" if n == 1 else f"{n} years"


def _terminal(draw, box, lines, accent, font_size=19, line_height=34, top_bar=True):
    """A dark terminal window. Lines are (text, colour) pairs; "$ " starts a prompt."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=14, fill="#050d17", outline="#1e3550", width=1)
    y = y0 + 22
    if top_bar:
        draw.rounded_rectangle((x0 + 1, y0 + 1, x1 - 1, y0 + 40), radius=13, fill="#0f2236")
        draw.rectangle((x0 + 1, y0 + 26, x1 - 1, y0 + 40), fill="#0f2236")
        for i, colour in enumerate(("#ff5f57", "#febc2e", "#28c840")):
            cx = x0 + 22 + i * 20
            draw.ellipse((cx - 6, y0 + 14, cx + 6, y0 + 26), fill=colour)
        y = y0 + 58
    regular, bold = _font("JetBrainsMono-Regular", font_size), _font("JetBrainsMono-Bold", font_size)
    for text, colour in lines:
        x = x0 + 24
        if text.startswith("$ "):
            draw.text((x, y), "$", font=bold, fill=accent)
            x += bold.getlength("$ ")
            text = text[2:]
        draw.text((x, y), text, font=regular, fill=colour)
        y += line_height


def _deploy(card: dict, photo) -> Image.Image:
    name, first, workspace = card["n"], _first(card["n"]), card["w"]
    img = Image.new("RGB", (WIDTH, HEIGHT), "#0b1a2b")
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((900, 360, 1320, 780), fill=(18, 135, 212, 30))
    img.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(img)
    img.paste(a := _avatar(photo, name, 132, ACCENT, 5, "#2d3a4a", "#ffffff"), (64, 56), a)
    _spaced(draw, (64, 214), "BIRTHDAY RELEASE", _font("Montserrat-Bold", 18), ACCENT, 2.9)
    y = 252 + _text(
        draw, (64, 252), f"Happy birthday, {first}", "Montserrat-ExtraBold", 54, 500, "#ffffff", smallest=36
    )
    y -= 50
    body = _font("Montserrat-Medium", 22)
    for line in _wrap("Deployed to production. Zero downtime. Cake in every region.", body, 480):
        draw.text((64, y + 70), line, font=body, fill="#9fb3c8")
        y += 31
    if workspace:
        _spaced(draw, (64, 520), workspace.upper(), _font("Montserrat-ExtraBold", 16), "#7c8b9b", 1.9)
    slug = _slug(first)
    _terminal(
        draw,
        (612, 100, 1136, 500),
        [
            (f"$ kubectl rollout status deploy/{slug}", "#c9d6e3"),
            ("Waiting for wishes from the team...", "#7d8fa3"),
            ("wishes: all replicas updated", "#7d8fa3"),
            (f'deployment "{slug}" rolled out', GREEN),
            ("", "#c9d6e3"),
            ("$ cat release-notes.md", "#c9d6e3"),
            ("+ cake", "#c9d6e3"),
            ("+ good wishes", "#c9d6e3"),
            ("- meetings (today only)", RED),
        ],
        ACCENT,
        font_size=18,
    )
    return img


def _merged(card: dict, photo) -> Image.Image:
    name, first, workspace = card["n"], _first(card["n"]), card["w"]
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f6f8fa")
    draw = ImageDraw.Draw(img)
    pill = _font("Montserrat-Bold", 18)
    draw.rounded_rectangle((64, 52, 64 + 40 + pill.getlength("Merged"), 92), radius=20, fill="#8250df")
    draw.text((84, 72), "Merged", font=pill, fill="#ffffff", anchor="lm")
    meta = _font("Montserrat-Medium", 18)
    mx = 64 + 56 + pill.getlength("Merged")
    draw.text((mx, 72), "by the whole team into", font=meta, fill="#59636e", anchor="lm")
    bx = mx + meta.getlength("by the whole team into ")
    mono = _font("JetBrainsMono-Regular", 17)
    draw.rounded_rectangle((bx, 58, bx + mono.getlength("life:main") + 16, 86), radius=6, fill="#ddf4ff")
    draw.text((bx + 8, 72), "life:main", font=mono, fill="#0969da", anchor="lm")
    head = f"feat: another great year for {first}"
    title = _fit(head, "Montserrat-ExtraBold", 54, 1072, smallest=36)
    _text(draw, (64, 120), head, "Montserrat-ExtraBold", 54, 1072, "#1f2328", lines=1, smallest=36)
    draw.text((64, 120 + title.size + 14), "#birthday", font=_font("Montserrat-Medium", 26), fill="#59636e")
    draw.rounded_rectangle((64, 260, 660, 548), radius=12, fill="#ffffff", outline="#d1d9e0")
    row = _font("Montserrat-Medium", 19)
    for i, (text, done) in enumerate(
        (
            ("All checks passed: kindness, curiosity, cake", True),
            ("Approved by everyone in the channel", True),
            ('Reviewer: "LGTM. Ship the cake."', False),
        )
    ):
        y = 312 + i * 72
        if done:
            draw.ellipse((92, y - 12, 116, y + 12), fill="#1a7f37")
            draw.line((98, y, 103, y + 5, 111, y - 5), fill="#ffffff", width=3)
        else:
            draw.ellipse((92, y - 12, 116, y + 12), outline="#59636e", width=2)
        draw.text((132, y), text, font=row, fill="#1f2328" if done else "#59636e", anchor="lm")
    draw.rounded_rectangle((690, 260, 1136, 548), radius=12, fill=ACCENT)
    img.paste(a := _avatar(photo, name, 100, "#ffffff", 4, "#2d3a4a", "#ffffff"), (718, 286), a)
    _spaced(draw, (836, 324), "HAPPY BIRTHDAY", _font("Montserrat-Bold", 16), "#dbeefa", 2.6)
    _text(draw, (718, 440), name, "Montserrat-ExtraBold", 40, 390, "#ffffff", smallest=28, middle=True)
    if workspace:
        _spaced(draw, (718, 510), workspace.upper(), _font("Montserrat-ExtraBold", 15), "#bfe0f5", 1.8)
    return img


def _terraform(card: dict, photo) -> Image.Image:
    name, years, workspace = card["n"], int(card.get("y") or 1), card["w"]
    slug = _slug(_first(name)).replace("-", "_")
    img = Image.new("RGB", (WIDTH, HEIGHT), "#160f2e")
    draw = ImageDraw.Draw(img)
    purple = "#a78bfa"
    draw.rounded_rectangle((64, 96, 620, 470), radius=14, fill="#0c0820", outline="#3a2d6b")
    mono, bold = _font("JetBrainsMono-Regular", 19), _font("JetBrainsMono-Bold", 19)
    x, y = 92, 124

    def line(parts, indent=0):
        nonlocal y
        cx = x + indent
        for text, colour, weight in parts:
            font = bold if weight else mono
            draw.text((cx, y), text, font=font, fill=colour)
            cx += font.getlength(text)
        y += 36

    line([("$ ", purple, True), (f"terraform apply -target={slug[:14]}", "#e8e4f7", False)])
    line([(f'# team["{slug[:18]}"]', "#8b84a8", False)])
    line([(f'~ resource "teammate" "{slug[:12]}" {{', "#e8e4f7", False)])
    line(
        [
            ("~ ", "#f2c744", False),
            (f"years = {years - 1} ", "#e8e4f7", False),
            ("-> ", "#8b84a8", False),
            (str(years), GREEN, False),
        ],
        28,
    )
    line([("+ ", GREEN, False), ('impact = "everywhere"', "#e8e4f7", False)], 28)
    line([("}", "#e8e4f7", False)])
    y += 8
    line(
        [
            ("Plan: ", "#e8e4f7", False),
            ("0 to add", GREEN, False),
            (", 1 to change, ", "#e8e4f7", False),
            ("0 to destroy", RED, False),
        ]
    )
    line([("Apply complete!", GREEN, True)])
    img.paste(a := _avatar(photo, name, 104, purple, 4, "#2d2550", "#ffffff"), (668, 90), a)
    _spaced(draw, (792, 130), "WORK ANNIVERSARY", _font("Montserrat-Bold", 18), purple, 2.9)
    big = _fit(_years(years), "Montserrat-ExtraBold", 108, 470, smallest=60)
    draw.text((668, 222), _years(years), font=big, fill="#ffffff")
    used = _text(draw, (668, 352), name, "Montserrat-ExtraBold", 40, 470, "#ffffff", smallest=26)
    draw.text(
        (668, 370 + used),
        "Still the best change we ever applied.",
        font=_fit("Still the best change we ever applied.", "Montserrat-Medium", 20, 470),
        fill="#b9b0d9",
    )
    if workspace:
        _spaced(draw, (668, 420 + used), workspace.upper(), _font("Montserrat-ExtraBold", 16), "#8a83a6", 1.9)
    return img


def _uptime(card: dict, photo) -> Image.Image:
    name, years, workspace = card["n"], int(card.get("y") or 1), card["w"]
    img = Image.new("RGB", (WIDTH, HEIGHT), "#0b1a2b")
    draw = ImageDraw.Draw(img)
    _spaced(draw, (64, 40), "WORK ANNIVERSARY", _font("Montserrat-Bold", 18), ACCENT, 2.9)
    if workspace:
        label = _font("Montserrat-ExtraBold", 16)
        width = sum(label.getlength(c) + 1.9 for c in workspace.upper())
        _spaced(draw, (int(1136 - width), 41), workspace.upper(), label, "#6f8193", 1.9)
    img.paste(a := _avatar(photo, name, 108, ACCENT, 5, "#2d3a4a", "#ffffff"), (64, 84), a)
    head = f"{name}, {_years(years)} in production"
    _text(draw, (196, 138), head, "Montserrat-ExtraBold", 52, 940, "#ffffff", smallest=30, middle=True)
    stats = (
        ("Uptime", "99.99%", GREEN, "The 0.01% was lunch"),
        ("Time with us", f"{years * 365:,} days", "#ffffff", "and counting"),
        ("SLA", "Renewed", ACCENT, "Auto-renews every year"),
    )
    for i, (label, value, colour, note) in enumerate(stats):
        x0 = 64 + i * 364
        draw.rounded_rectangle((x0, 226, x0 + 344, 420), radius=14, fill="#10263d", outline="#1e3550")
        draw.text((x0 + 24, 250), label, font=_font("Montserrat-Medium", 17), fill="#9fb3c8")
        draw.text((x0 + 24, 284), value, font=_fit(value, "Montserrat-ExtraBold", 50, 296, smallest=30), fill=colour)
        draw.text((x0 + 24, 370), note, font=_font("Montserrat-Medium", 15), fill="#9fb3c8")
    draw.rounded_rectangle((64, 462, 1136, 476), radius=7, fill="#10263d")
    draw.rounded_rectangle((64, 462, 1136, 476), radius=7, fill=ACCENT)
    labels = ["Joined", *(f"Year {n}" for n in range(1, years)), "Today"] if years <= 4 else ["Joined", "Today"]
    small = _font("Montserrat-Medium", 15)
    for i, text in enumerate(labels):
        x = 64 + (1072 * i) // (len(labels) - 1)
        anchor = "la" if i == 0 else "ra" if i == len(labels) - 1 else "ma"
        draw.text((x, 492), text, font=small, fill="#9fb3c8", anchor=anchor)
    return img


_DRAW = {"deploy": _deploy, "merged": _merged, "terraform": _terraform, "uptime": _uptime}


def render(card: dict, photo: Image.Image | None = None) -> bytes:
    """The card as a PNG."""
    image = _DRAW[card["d"]](card, photo)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def register_route(flask_app) -> None:
    """Draw a card. Public, as Slack fetches it without a session; the signature is the check."""
    from flask import Response, abort  # noqa: PLC0415

    def serve(signed: str):
        card = read_token(signed)
        if card is None:
            abort(404)
        try:
            png = render(card, _photo(card.get("a") or ""))
        except Exception:
            logger.exception("celebrations: could not draw a %s card", card.get("d"))
            abort(500)
        return Response(png, mimetype="image/png", headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}"})

    flask_app.add_url_rule(f"{ROUTE_PREFIX}/<signed>.png", "celebration_card", serve, methods=["GET"])
