CREATE TABLE IF NOT EXISTS chat_threads (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '新战术对话',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_message_at TIMESTAMPTZ,
    scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    scoped_video_title TEXT,
    agent_enabled BOOLEAN NOT NULL DEFAULT false,
    game_state JSONB
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed','interrupted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    agent_mode BOOLEAN NOT NULL DEFAULT false,
    error TEXT,
    UNIQUE(thread_id, request_id, role)
);

CREATE INDEX IF NOT EXISTS chat_messages_thread_order ON chat_messages(thread_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS chat_messages_one_running ON chat_messages(thread_id) WHERE status = 'running';
