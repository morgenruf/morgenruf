-- Unsubscribes, and a record of which follow-up has been sent.
--
-- The welcome email is transactional: somebody installed the app thirty
-- seconds earlier. The day-seven message asks a question, which makes it a
-- commercial electronic message under Canadian law, so it needs a working
-- unsubscribe and this is where that lives.
--
-- Suppression is by address rather than by workspace: a person who asks to be
-- left alone should be left alone everywhere, including from a workspace they
-- join later.
CREATE TABLE IF NOT EXISTS email_suppressions (
    email      TEXT PRIMARY KEY,
    reason     TEXT NOT NULL DEFAULT 'unsubscribed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One row per workspace per kind, so a follow-up cannot go twice. The kind is
-- recorded because the two variants say very different things and it matters
-- later which one somebody received.
CREATE TABLE IF NOT EXISTS install_emails (
    team_id    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    sent_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    to_email   TEXT,
    CONSTRAINT install_emails_once UNIQUE (team_id, kind)
);
