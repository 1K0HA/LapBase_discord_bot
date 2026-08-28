ALTER TABLE posts
ADD COLUMN IF NOT EXISTS telegram_media_message_ids BIGINT[] NOT NULL DEFAULT '{}'::BIGINT[];
