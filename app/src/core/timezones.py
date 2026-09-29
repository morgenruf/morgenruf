"""Canonical IANA timezone names.

Browsers (Chrome's Intl API returns "Asia/Calcutta") and older clients still
send names that the tz database keeps only as backward compatibility links.
Debian no longer ships those links in its system tz database, and APScheduler
resolves every trigger timezone through zoneinfo, so a stored "Asia/Calcutta"
raised ZoneInfoNotFoundError in production even though pytz accepted it.

The image now installs the tzdata package, which still carries the links.
Names are also rewritten to their canonical form when they are saved and when
a trigger is built, so a missing link can never stop a schedule from firing.
Migration 057_canonical_timezones.sql rewrites the same names in stored rows
and must be kept in step with LEGACY_TZ_ALIASES (a test checks this).
"""

from __future__ import annotations

# Legacy name to canonical name, taken from the tz database "backward" file.
# Limited to the names a browser, Slack or an older dashboard can realistically
# send; anything else is passed through unchanged.
LEGACY_TZ_ALIASES: dict[str, str] = {
    # Asia
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Dacca": "Asia/Dhaka",
    "Asia/Thimbu": "Asia/Thimphu",
    "Asia/Ujung_Pandang": "Asia/Makassar",
    "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Asia/Macao": "Asia/Macau",
    "Asia/Chongqing": "Asia/Shanghai",
    "Asia/Chungking": "Asia/Shanghai",
    "Asia/Harbin": "Asia/Shanghai",
    "Asia/Tel_Aviv": "Asia/Jerusalem",
    "Asia/Istanbul": "Europe/Istanbul",
    # Europe
    "Europe/Kiev": "Europe/Kyiv",
    "Europe/Uzhgorod": "Europe/Kyiv",
    "Europe/Zaporozhye": "Europe/Kyiv",
    "Europe/Belfast": "Europe/London",
    "Europe/Nicosia": "Asia/Nicosia",
    # Africa and Atlantic
    "Africa/Asmera": "Africa/Asmara",
    "Africa/Timbuktu": "Africa/Bamako",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    # Pacific
    "Pacific/Truk": "Pacific/Chuuk",
    "Pacific/Yap": "Pacific/Chuuk",
    "Pacific/Ponape": "Pacific/Pohnpei",
    "Pacific/Enderbury": "Pacific/Kanton",
    "Pacific/Samoa": "Pacific/Pago_Pago",
    # Americas
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Catamarca": "America/Argentina/Catamarca",
    "America/Cordoba": "America/Argentina/Cordoba",
    "America/Jujuy": "America/Argentina/Jujuy",
    "America/Mendoza": "America/Argentina/Mendoza",
    "America/Indianapolis": "America/Indiana/Indianapolis",
    "America/Fort_Wayne": "America/Indiana/Indianapolis",
    "America/Knox_IN": "America/Indiana/Knox",
    "America/Louisville": "America/Kentucky/Louisville",
    "America/Godthab": "America/Nuuk",
    "America/Montreal": "America/Toronto",
    "America/Nipigon": "America/Toronto",
    "America/Thunder_Bay": "America/Toronto",
    "America/Rainy_River": "America/Winnipeg",
    "America/Yellowknife": "America/Edmonton",
    "America/Pangnirtung": "America/Iqaluit",
    "America/Shiprock": "America/Denver",
    "America/Ensenada": "America/Tijuana",
    "America/Santa_Isabel": "America/Tijuana",
    "America/Porto_Acre": "America/Rio_Branco",
    "Australia/Currie": "Australia/Hobart",
    # Country and region style names
    "US/Eastern": "America/New_York",
    "US/Central": "America/Chicago",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "US/Alaska": "America/Anchorage",
    "US/Hawaii": "Pacific/Honolulu",
    "US/Arizona": "America/Phoenix",
    "US/East-Indiana": "America/Indiana/Indianapolis",
    "US/Indiana-Starke": "America/Indiana/Knox",
    "US/Michigan": "America/Detroit",
    "US/Aleutian": "America/Adak",
    "US/Samoa": "Pacific/Pago_Pago",
    "Canada/Atlantic": "America/Halifax",
    "Canada/Central": "America/Winnipeg",
    "Canada/Eastern": "America/Toronto",
    "Canada/Mountain": "America/Edmonton",
    "Canada/Newfoundland": "America/St_Johns",
    "Canada/Pacific": "America/Vancouver",
    "Canada/Saskatchewan": "America/Regina",
    "Brazil/East": "America/Sao_Paulo",
    "Mexico/General": "America/Mexico_City",
    "GB": "Europe/London",
    "Eire": "Europe/Dublin",
    "Poland": "Europe/Warsaw",
    "Portugal": "Europe/Lisbon",
    "Turkey": "Europe/Istanbul",
    "Egypt": "Africa/Cairo",
    "Iran": "Asia/Tehran",
    "Israel": "Asia/Jerusalem",
    "Japan": "Asia/Tokyo",
    "PRC": "Asia/Shanghai",
    "ROC": "Asia/Taipei",
    "ROK": "Asia/Seoul",
    "Hongkong": "Asia/Hong_Kong",
    "Singapore": "Asia/Singapore",
    "NZ": "Pacific/Auckland",
    "UCT": "Etc/UTC",
    "Universal": "Etc/UTC",
    "Zulu": "Etc/UTC",
    "Etc/UCT": "Etc/UTC",
    "Etc/Universal": "Etc/UTC",
    "Etc/Zulu": "Etc/UTC",
}


def canonical_tz(name: object) -> object:
    """Return the canonical IANA name for `name`.

    A known legacy name is rewritten ("Asia/Calcutta" becomes "Asia/Kolkata").
    Any other string comes back stripped of surrounding whitespace, and a
    non-string (None included) comes back unchanged, so callers can pass a raw
    payload value straight through.
    """
    if not isinstance(name, str):
        return name
    stripped = name.strip()
    return LEGACY_TZ_ALIASES.get(stripped, stripped)
