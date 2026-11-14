-- pgvector 初始化：由容器首次启动时自动执行（挂载到 /docker-entrypoint-initdb.d）
CREATE EXTENSION IF NOT EXISTS vector;

-- 视频元数据
CREATE TABLE IF NOT EXISTS videos (
    video_id    TEXT PRIMARY KEY,
    title       TEXT,
    author      TEXT,
    source      TEXT,
    chunk_count INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now()
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
    tokens     TEXT
);

-- 余弦相似度 HNSW 索引
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- 全文检索索引（simple 配置按空格分词，tokens 列为 jieba 空格分词）
CREATE INDEX IF NOT EXISTS chunks_tokens_tsv_idx
    ON chunks USING gin (to_tsvector('simple', tokens));

CREATE INDEX IF NOT EXISTS chunks_video_idx ON chunks(video_id);
