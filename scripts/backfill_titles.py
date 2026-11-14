"""一次性：给已入库的 B 站视频补齐真实标题与作者（此前入库标题存的是 BV 号）。"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
import config
from ingest.bili_fetcher import _session, _view_info


def main():
    dsn = (f"host={config.PG_HOST} port={config.PG_PORT} user={config.PG_USER} "
           f"password={config.PG_PASSWORD} dbname={config.PG_DB}")
    s = _session()
    with psycopg.connect(dsn) as c:
        rows = c.execute("SELECT video_id, title, author FROM videos").fetchall()
        for vid, old_title, old_author in rows:
            if not re.match(r"^BV[0-9A-Za-z]{10}$", vid):
                continue  # 本地视频跳过
            if old_title and old_title != vid and old_author:
                continue  # 已补齐
            try:
                info = _view_info(s, vid)
                title = info.get("title") or vid
                author = (info.get("owner") or {}).get("name") or ""
                c.execute(
                    "UPDATE videos SET title = %s, author = %s WHERE video_id = %s",
                    (title, author, vid),
                )
                print(f"  {vid}  ->  {title}   @{author}")
            except Exception as e:  # noqa: BLE001
                print(f"  {vid}  跳过: {e}")
        c.commit()


if __name__ == "__main__":
    main()
