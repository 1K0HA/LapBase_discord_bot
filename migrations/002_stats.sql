CREATE TABLE IF NOT EXISTS stats_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    discord_message_id BIGINT,
    discord_channel_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stats_created_at ON stats_events(created_at);
CREATE INDEX IF NOT EXISTS idx_stats_type_created ON stats_events(event_type, created_at);
