CREATE TABLE IF NOT EXISTS admin_confirmations (
    admin_user_id BIGINT PRIMARY KEY,
    action TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
