"""一次性迁移：把旧 Chroma(file) 中的向量与元数据导入 PostgreSQL + pgvector。

用法（项目根，video_rag 环境）：
    python scripts/migrate_chroma.py
"""
from pathlib import Path
import sys

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from index.store import add_chunks  # noqa: E402


def main() -> None:
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    col = client.get_collection(config.COLLECTION_NAME)
    got = col.get(include=["embeddings", "documents", "metadatas"])

    # 按 video_id 分组，沿用原 id 中的序号排序
    groups: dict = {}
    for _id, doc, emb, meta in zip(
        got["ids"], got["documents"], got["embeddings"], got["metadatas"]
    ):
        vid = meta["video_id"]
        order = int(_id.rsplit("-", 1)[1]) if "-" in _id else 0
        groups.setdefault(vid, []).append((order, doc, emb, meta))

    for vid, items in groups.items():
        items.sort(key=lambda x: x[0])
        chunks = [
            {"text": doc, "start": float(meta["start"]), "end": float(meta["end"])}
            for _, doc, _, meta in items
        ]
        embeddings = [emb for _, _, emb, _ in items]
        title = items[0][3].get("title") or vid
        source = items[0][3].get("source") or ""
        add_chunks(vid, chunks, embeddings, title=title, source=source)
        print(f"migrated {vid}: {len(chunks)} chunks")

    print("done.")


if __name__ == "__main__":
    main()
