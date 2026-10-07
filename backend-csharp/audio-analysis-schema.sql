-- Additive upgrade for existing EnsureCreated databases; no data is removed.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS risk_level text;
CREATE TABLE IF NOT EXISTS audio_analyses (
    id text PRIMARY KEY,
    device_id text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    audio_file_url text NOT NULL,
    result_json text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audio_analyses_created_at ON audio_analyses (created_at DESC);
