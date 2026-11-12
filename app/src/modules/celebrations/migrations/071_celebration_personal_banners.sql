-- Personal banners: a card with the person's photo, name and years, instead
-- of a stock image. Off by default, so existing workspaces see no change.

ALTER TABLE celebration_settings ADD COLUMN IF NOT EXISTS personal_banners BOOLEAN NOT NULL DEFAULT FALSE;
