"""向量存储：PostgreSQL + pgvector，持久化 embedding 与视频元数据。

对外保持与旧 Chroma 版相近的函数：add_chunks / list_videos / search / delete_video；
另提供 hybrid_search（向量 + 全文 RRF 融合）供混合检索使用。
"""
from contextlib import contextmanager

import psycopg

import config
from index.tokenizer import tokenize


def _dsn() -> str:
    return (
        f"host={config.PG_HOST} port={config.PG_PORT} user={config.PG_USER} "
        f"password={config.PG_PASSWORD} dbname={config.PG_DB}"
    )


@contextmanager
def _conn():
    with psycopg.connect(_dsn()) as c:
        yield c


def _vector_literal(vec: list) -> str:
    return "[" + ",".join(f"{x:.9f}" for x in vec) + "]"


def video_exists(video_id: str) -> bool:
    with _conn() as c:
        return c.execute("SELECT 1 FROM chunks WHERE video_id = %s LIMIT 1", (video_id,)).fetchone() is not None


@contextmanager
def lock_video_ingest(video_id: str):
    """同一视频的检查和导入跨进程串行，连接关闭时自动释放锁。"""
    with psycopg.connect(_dsn(), autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (video_id,))
        yield


def add_chunks(video_id: str, chunks: list, embeddings: list,
               title: str | None = None, source: str | None = None,
               author: str | None = None) -> None:
    """chunks: [{"text","start","end"}]，embeddings 与 chunks 一一对应。
    同一 video_id 重复导入时先清旧片段，避免重复污染检索。"""
    if not chunks:
        return
    title = title or video_id
    source = source or ""
    author = author or ""

    rows = [
        (
            video_id,
            i,
            c["text"],
            float(c["start"]),
            float(c["end"]),
            _vector_literal(embeddings[i]),
            tokenize(c["text"]),  # 全文检索用：空格分词串
        )
        for i, c in enumerate(chunks)
    ]

    with _conn() as c:
        c.execute(
            """
            INSERT INTO videos(video_id, title, author, source, chunk_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (video_id) DO UPDATE
              SET title = EXCLUDED.title,
                  author = EXCLUDED.author,
                  source = EXCLUDED.source,
                  chunk_count = EXCLUDED.chunk_count
            """,
            (video_id, title, author, source, len(chunks)),
        )
        c.execute("DELETE FROM chunks WHERE video_id = %s", (video_id,))
        c.cursor().executemany(
            """
            INSERT INTO chunks(video_id, chunk_idx, text, start_sec, end_sec, embedding, tokens)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
            """,
            rows,
        )
        c.commit()


def list_videos() -> list:
    """返回 [{video_id,title,source,chunk_count,duration}]，duration 由片段时间聚合。"""
    with _conn() as c:
        cur = c.execute(
            """
            SELECT v.video_id, v.title, v.author, v.source, v.chunk_count, v.created_at,
                   COALESCE(MAX(ch.end_sec) - MIN(ch.start_sec), 0) AS duration
            FROM videos v
            LEFT JOIN chunks ch ON ch.video_id = v.video_id
            GROUP BY v.video_id, v.title, v.author, v.source, v.chunk_count, v.created_at
            ORDER BY v.created_at DESC NULLS LAST, v.video_id
            """
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def search(embedding: list, top_k: int) -> list:
    """余弦距离检索（<=>），返回 [{text, meta, distance}]。"""
    qvec = _vector_literal(embedding)
    with _conn() as c:
        cur = c.execute(
            """
            SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                   v.source, ch.chunk_idx, ch.embedding <=> %s::vector AS distance
            FROM chunks ch
            JOIN videos v ON v.video_id = ch.video_id
            ORDER BY ch.embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, qvec, top_k),
        )
        hits = []
        for text, start, end, vid, title, author, source, chunk_idx, distance in cur.fetchall():
            hits.append({
                "text": text,
                "meta": {
                    "video_id": vid,
                    "title": title,
                    "author": author,
                    "source": source,
                    "start": float(start),
                    "end": float(end),
                    "chunk_idx": int(chunk_idx),
                },
                "distance": float(distance),
            })
        return hits


def delete_video(video_id: str) -> None:
    """删除视频（chunks 由外键 CASCADE 一并删除）。"""
    with _conn() as c:
        c.execute("DELETE FROM videos WHERE video_id = %s", (video_id,))
        c.commit()


# 混合检索参数
HYBRID_VEC_K = 50   # 向量通道候选数
HYBRID_BM_K = 50    # 全文通道候选数
RRF_K = 60          # RRF 常数


def _hits_from_rows(rows, lexical_keys=None) -> list:
    """把 (text,start,end,video_id,title,author,source,chunk_idx,distance) 行转成统一 hit 结构。

    lexical_keys: {(video_id, start)}，命中该 key 的 hit 标记 lexical=True（被全文通道召回，
    距离阈值过滤时应豁免——关键词精确命中是强相关信号，即使向量距离偏大也保留）。"""
    out = []
    for text, start, end, vid, title, author, source, chunk_idx, distance in rows:
        key = (vid, float(start))
        out.append({
            "text": text,
            "meta": {
                "video_id": vid,
                "title": title,
                "author": author,
                "source": source,
                "start": float(start),
                "end": float(end),
                "chunk_idx": int(chunk_idx),
            },
            "distance": float(distance),
            "lexical": bool(lexical_keys) and key in lexical_keys,
        })
    return out


def expand_neighbors(hits: list, window: int = 1) -> list:
    """把每个命中片段同视频的前后相邻片段并入其文本。

    字幕按固定字符窗口切分，一个完整操作常跨两个片段；只召回其中一半时回答会
    在句子中间断掉。这里按 (video_id, chunk_idx) 取前后 window 个相邻片段，
    拼成一段连续文本，时间范围随之扩展。相邻命中会被合并，避免重复。
    """
    if not hits:
        return hits
    vids = sorted({h["meta"]["video_id"] for h in hits})
    with _conn() as c:
        rows = c.execute(
            """
            SELECT video_id, chunk_idx, start_sec, end_sec, text
            FROM chunks WHERE video_id = ANY(%s)
            ORDER BY video_id, chunk_idx
            """,
            (vids,),
        ).fetchall()
    book: dict = {}
    for vid, idx, s, e, t in rows:
        book.setdefault(vid, {})[int(idx)] = (float(s), float(e), t)

    out = []
    covered = set()  # 已被并入某条结果的 (video_id, chunk_idx)
    for h in hits:
        m = h["meta"]
        vid, idx = m["video_id"], m["chunk_idx"]
        if (vid, idx) in covered:
            continue
        chunks = book.get(vid, {})
        idxs = [i for i in range(idx - window, idx + window + 1)
                if i in chunks and (vid, i) not in covered]
        if not idxs:
            idxs = [idx]
        new = {
            **h,
            "text": " ".join(chunks[i][2] for i in idxs),
            "meta": {
                **m,
                "start": min(chunks[i][0] for i in idxs),
                "end": max(chunks[i][1] for i in idxs),
            },
        }
        out.append(new)
        covered.update((vid, i) for i in idxs)
    return out


def hybrid_search(embedding: list, query_terms: str, top_k: int) -> list:
    """混合检索：向量 top vec_k + 全文(top bm_k) 各自取候选，RRF 融合后取 top_k。

    query_terms: 空格分词串（由 tokenizer.query_terms 生成）。为空则退化为纯向量。
    返回与 search 同构的 [{text, meta, distance}]。
    """
    qvec = _vector_literal(embedding)
    with _conn() as c:
        # 向量通道
        vec_rows = c.execute(
            """
            SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                   v.source, ch.chunk_idx, ch.embedding <=> %s::vector AS distance
            FROM chunks ch JOIN videos v ON v.video_id = ch.video_id
            ORDER BY ch.embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, qvec, HYBRID_VEC_K),
        ).fetchall()

        # 全文通道（simple 配置按空格分词，tokens 列已存空格分词）。
        # 用 AND 语义：只召回同时含多个查询信息词的 chunk，避免宽 OR 被高频词淹没。
        # 查询词过少（<2）或 AND 空结果时退化为纯向量（full_rows 空）。
        if query_terms.strip():
            qts = " & ".join(query_terms.split())
            full_rows = c.execute(
                """
                SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                       v.source, ch.chunk_idx, ch.embedding <=> %s::vector AS distance
                FROM chunks ch JOIN videos v ON v.video_id = ch.video_id
                WHERE to_tsvector('simple', ch.tokens) @@ to_tsquery('simple', %s)
                ORDER BY ts_rank_cd(to_tsvector('simple', ch.tokens), to_tsquery('simple', %s)) DESC
                LIMIT %s
                """,
                (qvec, qts, qts, HYBRID_BM_K),
            ).fetchall()
        else:
            full_rows = []

    # RRF 融合：chunk 身份用 (video_id, start) 作 key
    agg = {}
    for rank, row in enumerate(vec_rows, 1):
        key = (row[3], float(row[1]))
        agg[key] = agg.get(key, 0.0) + 1.0 / (RRF_K + rank)
    lexical_keys = set()
    for rank, row in enumerate(full_rows, 1):
        key = (row[3], float(row[1]))
        agg[key] = agg.get(key, 0.0) + 1.0 / (RRF_K + rank)
        lexical_keys.add(key)

    merged = {key: row for key, row in
              [( (r[3], float(r[1])), r) for r in vec_rows + full_rows]}
    top_keys = [k for k, _ in sorted(agg.items(), key=lambda x: -x[1])[:top_k]]
    return _hits_from_rows([merged[k] for k in top_keys], lexical_keys)
