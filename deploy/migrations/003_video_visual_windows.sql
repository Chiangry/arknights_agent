CREATE TABLE IF NOT EXISTS video_visual_windows (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    start_sec DOUBLE PRECISION NOT NULL,
    end_sec DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('indexed', 'empty', 'failed')),
    error TEXT,
    PRIMARY KEY (video_id, start_sec, end_sec)
);
