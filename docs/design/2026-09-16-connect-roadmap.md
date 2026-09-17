# Roadmap: Donut parity modules

Date: 2026-09-16
Status: Roadmap. Each sub-project gets its own spec before implementation.

## Position

Donut has moved upmarket: Journeys (AI onboarding), HRIS and ATS sync, rewards,
Gatheround, plus Microsoft Teams and FigJam. Their simple coffee-chat bot is now
one pillar of an enterprise platform.

That is the opening. A simple, self-hosted, no-per-seat pairing bot is a
product they have effectively vacated.

## Pillars

Donut has five. One is already shipped.

| # | Pillar | Morgenruf status | Sub-project |
|---|---|---|---|
| 1 | Introductions (pairing) | Not built | Connect, spec written |
| 2 | Recognition (Shoutouts) | **Already shipped** as `kudos` (migration 010, `db.py:1560-1607`, DM and slash command) | Package as a module in Phase 0, then market it |
| 3 | Engagement (watercooler prompts) | Not built | Sub-project 2 |
| 4 | Onboarding (intros, buddies) | Not built | Sub-projects 3 and 4 |
| 5 | Celebrations | Not built | Sub-project 5 |

## Build order and rationale

**Phase 0: module contract.** Prerequisite for everything. See
`2026-09-16-connect-pairing-design.md`.

**1. Connect (pairing).** The thing teams actually pay Donut for, and the
hardest logic (matching, odd counts, repeat avoidance, rate-limited delivery).
Everything else is easier once it exists. Spec written.

**2. Watercooler.** Cheapest of the remaining four. Scheduled prompts to a
channel with a prompt library and rotation. Reuses the scheduler and the
existing channel-post code almost unchanged. Fast win directly after Connect.

**3. Intros.** New member joins, bot posts a profile card to a channel. Small,
but it introduces the `team_join` event listener that sub-project 4 depends on.
Requires adding the `team_join` event subscription to the manifest.

**4. Onboarding buddies.** New hire matched to a veteran, with a multi-week
checklist. A variant of pairing with a fixed-role constraint, so it is nearly
free once Connect's matching engine exists. Depends on both Connect and Intros.

**5. Celebrations.** Birthdays and work anniversaries. Deliberately last,
because it is blocked on a data problem rather than a code problem. It needs
every member's dates, which means a collection flow (DM prompt, dashboard
entry, CSV import) and it is PII with retention implications. The code is easy;
the data and privacy design is not.

## Marketing note

Recognition is already built. Once `kudos` is packaged as a module in Phase 0,
it can be positioned as a Donut Shoutouts alternative with no further
engineering. That is the cheapest competitive claim available and it should not
wait for Connect.

A `/donut-alternative` comparison page is worth building regardless of module
progress, since it is independent of the engineering work.
