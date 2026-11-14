"""迁移：chunks 表加 tokens 列(空格分词)并填充现有 chunk，建全文索引。

一次性，供混合检索(向量+全文)使用。用法: python scripts/migrate_tokens.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
import config
from index.tokenizer import tokenize


def main():
    dsn = (f"host={config.PG_HOST} port={config.PG_PORT} user={config.PG_USER} "
           f"password={config.PG_PASSWORD} dbname={config.PG_DB}")
    with psycopg.connect(dsn) as c:
        # 1. 加列
        c.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tokens TEXT")
        # 2. 填充现有 chunk（只填空值，避免覆盖）
        rows = c.execute(
            "SELECT id, text FROM chunks WHERE tokens IS NULL OR tokens = ''"
        ).fetchall()
        print(f"待填充 tokens 的 chunk: {len(rows)}")
        for cid, text in rows:
            c.execute("UPDATE chunks SET tokens = %s WHERE id = %s",
                      (tokenize(text), cid))
        # 3. 全文索引（simple 配置按空格分词）
        c.execute("""
            CREATE INDEX IF NOT EXISTS chunks_tokens_tsv_idx
            ON chunks USING gin (to_tsvector('simple', tokens))
        """)
        c.commit()
    print("迁移完成：tokens 列已填充，全文索引已建。")


if __name__ == "__main__":
    main()
