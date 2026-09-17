-- Outbound webhook delivery log, plus a one-off normalisation of event names.
--
-- Every attempt made by handlers.fire_webhooks lands here, success or failure,
-- so an operator can see whether their endpoint is actually receiving events
-- and whether the delivery was signed. status_code is NULL when the request
-- never produced a response (DNS failure, connection refused, timeout) and
-- error then holds a short reason. Retention is capped in application code
-- (db.record_webhook_delivery prunes to the most recent N rows per webhook).
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id BIGSERIAL PRIMARY KEY,
    webhook_id INTEGER NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    team_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status_code INTEGER,                     -- NULL when there was no HTTP response
    ok BOOLEAN NOT NULL DEFAULT FALSE,       -- TRUE for a 2xx response
    signed BOOLEAN NOT NULL DEFAULT FALSE,   -- was X-Morgenruf-Signature sent
    error TEXT,                              -- short failure description
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS webhook_deliveries_hook_idx
    ON webhook_deliveries(webhook_id, id DESC);
CREATE INDEX IF NOT EXISTS webhook_deliveries_team_idx
    ON webhook_deliveries(team_id, created_at DESC);

-- Settle the event naming convention on the dotted form the webhooks table has
-- used since migration 003. Rows written with the workflow_rules underscore
-- spelling are rewritten in place; db.normalize_webhook_events keeps accepting
-- the underscore form on input.
UPDATE webhooks
SET events = ARRAY(
        SELECT CASE e
            WHEN 'standup_complete'  THEN 'standup.completed'
            WHEN 'standup_completed' THEN 'standup.completed'
            WHEN 'blocker_detected'  THEN 'blocker.detected'
            WHEN 'low_participation' THEN 'participation.low'
            ELSE e
        END
        FROM unnest(events) AS e
    )
WHERE events && ARRAY['standup_complete', 'standup_completed', 'blocker_detected', 'low_participation'];

ALTER TABLE webhooks ALTER COLUMN events SET DEFAULT ARRAY['standup.completed']::TEXT[];
