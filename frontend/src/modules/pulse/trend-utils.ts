import type { PulseRound } from '@/common/api/generated/data-contracts';

/** Chart rows, oldest first. A hidden or still open round is a gap: its numbers are null. */
/** Why a week shows no number, in the words the page uses. */
export function gapReason(point: { open: boolean }) {
  return point.open
    ? 'Still open. Results show when it closes'
    : 'Fewer than 5 answers';
}

export function trendData(rounds: PulseRound[]) {
  return rounds.map((round, index) => ({
    index,
    sent_on: round.sent_on,
    hidden: round.hidden,
    open: !!round.open,
    respondents: round.respondents,
    invited: round.invited,
    rate: round.invited
      ? Math.round((round.respondents / round.invited) * 100)
      : null,
    mood: round.hidden ? null : (round.mood_avg ?? null),
    enps: round.hidden ? null : (round.enps ?? null),
  }));
}
