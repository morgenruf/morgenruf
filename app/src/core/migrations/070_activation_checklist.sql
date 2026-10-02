/* The activation checklist on the installer's Home tab.

   Every step is computed from data already stored; this keeps only what the
   checklist itself decides: whether an admin hid it, and the day "Send it
   now" last fired, so a second press the same day does not send twice. */
CREATE TABLE IF NOT EXISTS activation_checklist (
    team_id     TEXT PRIMARY KEY REFERENCES installations(team_id) ON DELETE CASCADE,
    hidden_at   TIMESTAMPTZ,
    hidden_by   TEXT,
    sent_now_on DATE
);
