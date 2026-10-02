-- Celebration banners: an image on each birthday and anniversary post.
--
-- Additive only. `banners` is on by default; `banner` records which image a
-- post used, so the next post of that kind picks a different one.

ALTER TABLE celebration_settings ADD COLUMN IF NOT EXISTS banners BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE celebration_posts ADD COLUMN IF NOT EXISTS banner TEXT;
