-- pgvector 初始化：由容器首次启动时自动执行（挂载到 /docker-entrypoint-initdb.d）
CREATE EXTENSION IF NOT EXISTS vector;

-- 视频元数据
CREATE TABLE IF NOT EXISTS videos (
    video_id    TEXT PRIMARY KEY,
    title       TEXT,
    author      TEXT,
    source      TEXT,
    chunk_count INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now(),
    game_id TEXT,
    category_id TEXT,
    stage_name TEXT,
    source_platform TEXT,
    source_url TEXT,
    cover_url TEXT,
    duration_seconds DOUBLE PRECISION,
    published_at TIMESTAMPTZ,
    indexed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now(),
    description TEXT,
    summary TEXT
);

-- 文本片段 + bge-m3 向量（1024 维）+ 全文分词（混合检索）
CREATE TABLE IF NOT EXISTS chunks (
    id         BIGSERIAL PRIMARY KEY,
    video_id   TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    chunk_idx  INTEGER NOT NULL,
    text       TEXT NOT NULL,
    start_sec  DOUBLE PRECISION,
    end_sec    DOUBLE PRECISION,
    embedding  vector(1024) NOT NULL,
    tokens     TEXT,
    evidence_source TEXT,
    original_text TEXT
);

-- 余弦相似度 HNSW 索引
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- 全文检索索引（simple 配置按空格分词，tokens 列为 jieba 空格分词）
CREATE INDEX IF NOT EXISTS chunks_tokens_tsv_idx
    ON chunks USING gin (to_tsvector('simple', tokens));

CREATE INDEX IF NOT EXISTS chunks_video_idx ON chunks(video_id);
CREATE INDEX IF NOT EXISTS videos_scope_idx ON videos(game_id, category_id);

CREATE TABLE IF NOT EXISTS video_visual_windows (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    start_sec DOUBLE PRECISION NOT NULL,
    end_sec DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('indexed', 'empty', 'failed')),
    error TEXT,
    PRIMARY KEY (video_id, start_sec, end_sec)
);

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
