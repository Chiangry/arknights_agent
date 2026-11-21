-- 保存专名校对前的正文；不重写旧切片、不改变向量索引。
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS original_text TEXT;
