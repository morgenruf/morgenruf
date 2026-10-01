import type { PulseRound } from '@/common/api/generated/data-contracts';

/** Chart rows, oldest first. A hidden round is a gap: its numbers are null. */
export function trendData(rounds: PulseRound[]) {
  return rounds.map((round, index) => ({
    index,
    sent_on: round.sent_on,
    hidden: round.hidden,
    respondents: round.respondents,
    invited: round.invited,
    rate: round.invited
      ? Math.round((round.respondents / round.invited) * 100)
      : null,
    mood: round.hidden ? null : (round.mood_avg ?? null),
    enps: round.hidden ? null : (round.enps ?? null),
  }));
}
