-- 空值沿用视频的字幕来源，不重写旧切片。
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS evidence_source TEXT;
