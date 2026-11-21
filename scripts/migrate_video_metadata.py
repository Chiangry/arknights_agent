"""运行：python -m scripts.migrate_video_metadata（先备份数据库）。"""
from pathlib import Path
from index.store import _conn


def migrate():
    migrations = Path(__file__).resolve().parents[1] / "deploy/migrations"
    with _conn() as conn:
        before = conn.execute("SELECT (SELECT count(*) FROM videos), (SELECT count(*) FROM chunks)").fetchone()
        for path in sorted(migrations.glob("*.sql")):
            conn.execute(path.read_text())
        after = conn.execute("SELECT (SELECT count(*) FROM videos), (SELECT count(*) FROM chunks)").fetchone()
        if before != after:
            raise RuntimeError("迁移计数不一致，事务回滚")
    print(f"迁移完成：videos={after[0]}, chunks={after[1]}，未修改向量及字幕")


if __name__ == "__main__":
    migrate()
