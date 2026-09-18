-- The rest of the settings a coffee chat needs, from the shape Donut's own
-- settings page has: group size, what the introduction sounds like, how they
-- are expected to meet, and when the next round falls.
--
-- Every default is what the module already did, so upgrading changes nothing:
-- pairs, a hybrid-team wording, a shared room link if one is set, and the next
-- round falling out of the cadence rather than being pinned.
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS group_size INT NOT NULL DEFAULT 2;
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS strict_group_size BOOLEAN NOT NULL DEFAULT FALSE;

-- hybrid | remote | in_person. Changes the wording, not the mechanics: a
-- distributed team and one that shares an office need different sentences for
-- the same introduction.
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS intro_tone TEXT NOT NULL DEFAULT 'hybrid';

-- link | zoom | none. "link" is the shared meeting_link this module has always
-- had; "zoom" schedules on a linked account once a time is agreed.
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS video_mode TEXT NOT NULL DEFAULT 'link';

-- Pin the next round to a date instead of letting the cadence decide. Null
-- means the cadence decides, which is what every existing programme does.
ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS next_round_date DATE;

ALTER TABLE connect_programs
    ADD COLUMN IF NOT EXISTS include_guests BOOLEAN NOT NULL DEFAULT FALSE;

-- A value outside the set would reach the matcher and be silently coerced, so
-- the column refuses it instead.
ALTER TABLE connect_programs DROP CONSTRAINT IF EXISTS connect_programs_group_size_sane;
ALTER TABLE connect_programs
    ADD CONSTRAINT connect_programs_group_size_sane CHECK (group_size BETWEEN 2 AND 8);
ALTER TABLE connect_programs DROP CONSTRAINT IF EXISTS connect_programs_intro_tone_known;
ALTER TABLE connect_programs
    ADD CONSTRAINT connect_programs_intro_tone_known CHECK (intro_tone IN ('hybrid', 'remote', 'in_person'));
ALTER TABLE connect_programs DROP CONSTRAINT IF EXISTS connect_programs_video_mode_known;
ALTER TABLE connect_programs
    ADD CONSTRAINT connect_programs_video_mode_known CHECK (video_mode IN ('link', 'zoom', 'none'));
