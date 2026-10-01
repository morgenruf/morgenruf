/* Counts for workspace history: polls created and pulse rounds sent. No
   answers, votes or names. */
ALTER TABLE workspace_history ADD COLUMN IF NOT EXISTS polls_created INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workspace_history ADD COLUMN IF NOT EXISTS pulse_rounds INTEGER NOT NULL DEFAULT 0;
