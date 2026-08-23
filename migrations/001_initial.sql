CREATE TABLE IF NOT EXISTS posts (
    discord_message_id BIGINT PRIMARY KEY,
    discord_channel_id BIGINT NOT NULL,
    telegram_message_id BIGINT,
    status TEXT NOT NULL CHECK (status IN ('queued','processing','retrying','published','failed','deleted')),
    pending_action TEXT NOT NULL DEFAULT 'publish' CHECK (pending_action IN ('publish','edit','delete','republish')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ,
    source_created_at TIMESTAMPTZ NOT NULL,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_posts_status_queue ON posts(status, queued_at);
CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(discord_channel_id);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO system_state(key, value)
VALUES('mode', 'running')
ON CONFLICT(key) DO NOTHING;
