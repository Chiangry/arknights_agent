-- 增量且可重复执行；不重写字幕、向量或历史分类。
ALTER TABLE videos ADD COLUMN IF NOT EXISTS game_id TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS category_id TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS stage_name TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_platform TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS cover_url TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS duration_seconds DOUBLE PRECISION;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE videos ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS summary TEXT;
UPDATE videos SET source_platform = CASE WHEN video_id ~ '^BV[0-9A-Za-z]{10}$' THEN 'bilibili' ELSE 'local' END
WHERE source_platform IS NULL;
UPDATE videos SET source_url = 'https://www.bilibili.com/video/' || video_id || '/'
WHERE source_platform = 'bilibili' AND source_url IS NULL;
UPDATE videos SET indexed_at = created_at WHERE indexed_at IS NULL
AND EXISTS (SELECT 1 FROM chunks WHERE chunks.video_id = videos.video_id);
CREATE INDEX IF NOT EXISTS videos_scope_idx ON videos(game_id, category_id);
