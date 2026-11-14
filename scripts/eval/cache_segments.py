"""抓取 B 站视频的原始字幕条目并缓存到 JSON，供切分实验离线复用。

缓存结构: { "video_id": {"title": str, "segments": [[start, end, text], ...]}, ... }
用法: python scripts/eval/cache_segments.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.bili_fetcher import fetch_subtitles

VIDEOS = [
    "BV1SfpF6GEzC",
    "BV1n9uq6NEWu",
    "BV1VA8a6xE93",
    "BV19P4w6aEk3",
    "BV1G9KJ68EWV",
]

OUT = Path(__file__).parent / "segments_cache.json"


def main():
    cache = {}
    if OUT.exists():
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    for vid in VIDEOS:
        if vid in cache:
            print(f"  {vid}: 已缓存 {len(cache[vid]['segments'])} 条，跳过")
            continue
        segments, source, title, author = fetch_subtitles(f"https://www.bilibili.com/video/{vid}")
        if not segments:
            print(f"  {vid}: 未取到字幕，跳过")
            continue
        # 转成 JSON 安全的 list
        seg = [[round(s, 1), round(e, 1), t] for s, e, t in segments]
        cache[vid] = {"title": title, "author": author, "source": source, "segments": seg}
        print(f"  {vid}: {len(seg)} 条字幕 @{author}")
    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n缓存已写入 {OUT}")


if __name__ == "__main__":
    main()
