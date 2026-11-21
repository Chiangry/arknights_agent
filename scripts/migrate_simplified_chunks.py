"""用本地 OpenCC 迁移旧切片正文与全文检索词，默认只预览。"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from index.store import _conn
from index.tokenizer import tokenize
from text_normalization import to_simplified


def migrate(conn, *, video_id: str | None = None, apply: bool = False) -> tuple[int, int, int]:
    last_id = scanned = changed = updated = 0
    while True:
        rows = conn.execute(
            "SELECT id, text, tokens FROM chunks WHERE id > %s "
            "AND (%s::text IS NULL OR video_id = %s) ORDER BY id LIMIT 500",
            (last_id, video_id, video_id),
        ).fetchall()
        if not rows:
            return scanned, changed, updated
        last_id = rows[-1][0]
        scanned += len(rows)
        updates = []
        for chunk_id, text, old_tokens in rows:
            simplified = to_simplified(text)
            tokens = tokenize(simplified)
            if simplified != text or tokens != old_tokens:
                updates.append((simplified, tokens, chunk_id, text, old_tokens))
        changed += len(updates)
        if apply and updates:
            with conn.cursor() as cursor:
                cursor.executemany(
                    "UPDATE chunks SET text = %s, tokens = %s WHERE id = %s "
                    "AND text = %s AND tokens IS NOT DISTINCT FROM %s",
                    updates,
                )
                updated += cursor.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-id", help="只处理指定视频；省略则扫描全库")
    parser.add_argument("--apply", action="store_true", help="实际写入；省略则只读预览")
    args = parser.parse_args()
    with _conn() as conn:
        if not args.apply:
            conn.execute("SET TRANSACTION READ ONLY")
        scanned, changed, updated = migrate(conn, video_id=args.video_id, apply=args.apply)
    print(f"扫描 {scanned} 条；需转换或重建分词 {changed} 条；实际写入 {updated} 条。")
    if args.apply and updated != changed:
        print("部分切片在迁移期间发生变动，未覆盖；可重跑。")


if __name__ == "__main__":
    main()
