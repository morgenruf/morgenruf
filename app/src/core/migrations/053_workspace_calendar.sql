-- The workspace calendar: which weekdays the company works, and its holidays.
--
-- Core rather than Celebrations data, because Onboarding buddies reads the
-- same calendar and one module must not read another's settings. It is
-- edited from the Celebrations settings page for now.
--
-- Additive only. working_days uses the same "mon,tue,..." spelling as
-- schedule_days, and the default is the Monday to Friday week every
-- workspace had implicitly until now. Standup does not read this column.
ALTER TABLE workspace_config
    ADD COLUMN IF NOT EXISTS working_days TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri';

-- One row per company holiday. Morgenruf ships no holiday calendar of its
-- own: the company's list is the only source. Rows older than a year are
-- purged nightly, since nothing looks back that far.
CREATE TABLE IF NOT EXISTS workspace_holidays (
    team_id    TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    date       DATE NOT NULL,
    name       TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, date)
);

CREATE INDEX IF NOT EXISTS idx_workspace_holidays_date ON workspace_holidays (date);
