"""向量存储：PostgreSQL + pgvector，持久化 embedding 与视频元数据。

对外保持与旧 Chroma 版相近的函数：add_chunks / list_videos / search / delete_video；
另提供 hybrid_search（向量 + 全文 RRF 融合）供混合检索使用。
"""
from contextlib import contextmanager

import psycopg
from psycopg import sql
from index.catalog import RetrievalScope, VideoMetadata

import config
from index.tokenizer import tokenize
from text_normalization import to_simplified


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
            to_simplified(c["text"]),
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
              SET title = COALESCE(NULLIF(videos.title, ''), EXCLUDED.title),
                  author = COALESCE(NULLIF(videos.author, ''), EXCLUDED.author),
                  source = EXCLUDED.source,
                  chunk_count = EXCLUDED.chunk_count,
                  indexed_at = now(), updated_at = now()
            """,
            (video_id, title, author, source, len(chunks)),
        )
        c.execute("DELETE FROM chunks WHERE video_id = %s", (video_id,))
        c.execute("""UPDATE videos SET indexed_at = now(),
            source_platform = COALESCE(source_platform, CASE WHEN video_id LIKE 'BV%%' THEN 'bilibili' ELSE 'local' END),
            source_url = COALESCE(source_url, CASE WHEN video_id LIKE 'BV%%' THEN 'https://www.bilibili.com/video/' || video_id || '/' END)
            WHERE video_id = %s""", (video_id,))
        c.cursor().executemany(
            """
            INSERT INTO chunks(video_id, chunk_idx, text, start_sec, end_sec, embedding, tokens)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
            """,
            rows,
        )
        c.commit()


def list_videos(scope: RetrievalScope | None = None, query: str = "", limit: int | None = None, offset: int = 0) -> list:
    """返回 [{video_id,title,source,chunk_count,duration}]，duration 由片段时间聚合。"""
    where, params = scope_filter(scope)
    if query:
        where += " AND concat_ws(' ', v.title, v.author, v.video_id, v.stage_name) ILIKE %s"
        params.append('%' + query + '%')
    with _conn() as c:
        cur = c.execute(
            f"""
            SELECT v.*, COUNT(ch.id)::int AS actual_chunk_count,
                   COALESCE(v.duration_seconds, MAX(ch.end_sec), 0) AS duration
            FROM videos v
            LEFT JOIN chunks ch ON ch.video_id = v.video_id
            WHERE {where}
            GROUP BY v.video_id
            ORDER BY v.created_at DESC NULLS LAST, v.video_id
            LIMIT %s OFFSET %s
            """, (*params, limit, offset),
        )
        cols = [d.name for d in cur.description]
        result = [dict(zip(cols, r)) for r in cur.fetchall()]
        for video in result:
            video['chunk_count'] = video.pop('actual_chunk_count')
        return result


def _set_visual_window(conn, video_id: str, start: float, end: float, status: str, error=None):
    conn.execute("""
        INSERT INTO video_visual_windows(video_id,start_sec,end_sec,status,error)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (video_id,start_sec,end_sec)
        DO UPDATE SET status=EXCLUDED.status,error=EXCLUDED.error
    """, (video_id, start, end, status, error))


def save_failed_visual_window(video_id: str, start: float, end: float, error: str):
    with _conn() as conn:
        _set_visual_window(conn, video_id, start, end, "failed", error)


def list_visual_windows(video_id: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT start_sec,end_sec,status,error FROM video_visual_windows
            WHERE video_id=%s ORDER BY start_sec,end_sec
        """, (video_id,)).fetchall()
    return [dict(zip(("start", "end", "status", "reason"), row)) for row in rows]


def has_chunk_source(video_id: str, source: str) -> bool:
    with _conn() as conn:
        return conn.execute("""
            SELECT EXISTS(SELECT 1 FROM chunks ch JOIN videos v USING (video_id)
            WHERE ch.video_id=%s AND COALESCE(ch.evidence_source,v.source)=%s)
        """, (video_id, source)).fetchone()[0]


def list_chunk_references(video_id: str, sources: tuple[str, ...]) -> list[dict]:
    """只加载同一视频中可用于校对的来源，不把旧口述当作正确拼写。"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT text, evidence_source FROM chunks WHERE video_id=%s AND evidence_source=ANY(%s)",
            (video_id, list(sources)),
        ).fetchall()
    return [{"text": text, "evidence_source": source} for text, source in rows]


def append_evidence_chunks(video_id: str, chunks: list, embeddings: list, *, window=None) -> int:
    """仅追加不同的来源证据，保留已有字幕和向量。"""
    if len(chunks) != len(embeddings):
        raise ValueError("证据与向量数量不一致")
    with _conn() as conn:
        conn.execute("SELECT video_id FROM videos WHERE video_id=%s FOR UPDATE", (video_id,))
        rows = conn.execute("""SELECT chunk_idx, text, start_sec, end_sec, evidence_source
                              FROM chunks WHERE video_id=%s""", (video_id,)).fetchall()
        known = {(to_simplified(text), a, b, source) for _, text, a, b, source in rows}
        next_idx = max((r[0] for r in rows), default=-1) + 1
        batch = []
        originals = []
        for c, vec in zip(chunks, embeddings):
            key = (to_simplified(c["text"]), round(c["start"], 2), round(c["end"], 2), c["evidence_source"])
            if key in known:
                continue
            known.add(key)
            text, a, b, source = key
            batch.append((video_id, next_idx, text, a, b, _vector_literal(vec), tokenize(text), source))
            if c.get("original_text"):
                originals.append((c["original_text"], video_id, next_idx))
            next_idx += 1
        if batch:
            conn.cursor().executemany("""
                INSERT INTO chunks(video_id, chunk_idx, text, start_sec, end_sec, embedding, tokens, evidence_source)
                VALUES (%s,%s,%s,%s,%s,%s::vector,%s,%s)
            """, batch)
            if originals:
                conn.cursor().executemany(
                    "UPDATE chunks SET original_text=%s WHERE video_id=%s AND chunk_idx=%s", originals,
                )
            conn.execute("""UPDATE videos SET chunk_count=(SELECT count(*) FROM chunks WHERE video_id=%s),
                            indexed_at=COALESCE(indexed_at,now()), updated_at=now() WHERE video_id=%s""",
                         (video_id, video_id))
        if window is not None:
            _set_visual_window(conn, video_id, *window, "indexed" if chunks else "empty")
        return len(batch)


def scope_filter(scope: RetrievalScope | None):
    """仅拼接受控字段名，所有值参数化。两路召回共用同一过滤器。"""
    clauses, params = ['TRUE'], []
    if scope:
        for name in ('game_id', 'category_id'):
            if value := getattr(scope, name):
                clauses.append(f'v.{name} = %s')
                params.append(value)
        if scope.video_ids:
            clauses.append('v.video_id = ANY(%s)')
            params.append(scope.video_ids)
    return ' AND '.join(clauses), params


def get_video(video_id: str):
    return next(iter(list_videos(RetrievalScope(video_ids=[video_id]))), None)


def list_video_chunks(video_id: str, query: str, limit: int, offset: int) -> dict | None:
    """读取索引里的原始切片，不走问答检索、精排或相邻扩展。"""
    with _conn() as conn:
        result = conn.execute("""
            WITH target AS (SELECT video_id, source FROM videos WHERE video_id = %s),
            matched AS (
                SELECT ch.id::text AS id, ch.chunk_idx, ch.start_sec, ch.end_sec, ch.text,
                       COALESCE(NULLIF(ch.evidence_source, ''), NULLIF(target.source, '')) AS source
                FROM chunks ch JOIN target USING (video_id)
                WHERE strpos(lower(ch.text), lower(%s)) > 0
            ),
            page AS (
                SELECT * FROM matched
                ORDER BY start_sec NULLS LAST, chunk_idx, id
                LIMIT %s OFFSET %s
            )
            SELECT (SELECT count(*) FROM matched),
                   COALESCE((SELECT json_agg(page ORDER BY start_sec NULLS LAST, chunk_idx, id) FROM page), '[]'::json)
            FROM target
            """, (video_id, query, limit, offset)).fetchone()
    return {"total": result[0], "chunks": result[1]} if result is not None else None


def retrieval_video_catalog(scope: RetrievalScope | None = None) -> list[dict]:
    """只读已有片段的视频；保留范围外名称以识别显式条件冲突。"""
    where, params = scope_filter(scope)
    with _conn() as conn:
        cur = conn.execute(f"""
            SELECT v.video_id, v.author, v.title, v.stage_name, LEFT(v.description, 2000) AS description,
                   v.published_at, ({where}) IS TRUE AS eligible
            FROM videos v WHERE EXISTS (SELECT 1 FROM chunks ch WHERE ch.video_id = v.video_id)
        """, params)
        fields = [column.name for column in cur.description]
        return [dict(zip(fields, row)) for row in cur.fetchall()]


def save_video_metadata(video_id: str, values: dict, *, create: bool = False):
    """PATCH 时合并后校验；行锁避免并发修改造成跨游戏分类。"""
    allowed = set(VideoMetadata.model_fields)
    if set(values) - allowed:
        raise ValueError('不支持的元数据字段')
    with _conn() as conn:
        if create:
            conn.execute("INSERT INTO videos(video_id, source_platform, source_url) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                         (video_id, 'bilibili' if video_id.startswith('BV') else 'local',
                          f'https://www.bilibili.com/video/{video_id}/' if video_id.startswith('BV') else None))
        row = conn.execute('SELECT game_id, category_id FROM videos WHERE video_id=%s FOR UPDATE', (video_id,)).fetchone()
        if row is None:
            raise KeyError(video_id)
        validated = VideoMetadata.model_validate({'game_id': row[0], 'category_id': row[1], **values})
        values = {key: getattr(validated, key) for key in values}
        if values:
            assignments = sql.SQL(', ').join(sql.SQL('{} = %s').format(sql.Identifier(k)) for k in values)
            conn.execute(sql.SQL('UPDATE videos SET {}, updated_at=now() WHERE video_id=%s').format(assignments),
                         (*values.values(), video_id))


def enrich_video_metadata(video_id: str, values: dict):
    """平台信息仅填补空值，不覆盖用户修改的标题/作者。"""
    allowed = {'title', 'author', 'cover_url', 'published_at', 'duration_seconds', 'description'}
    with _conn() as conn:
        for name, value in values.items():
            if name not in allowed or value is None:
                continue
            conn.execute(sql.SQL('UPDATE videos SET {k}=%s, updated_at=now() WHERE video_id=%s AND {k} IS NULL')
                         .format(k=sql.Identifier(name)), (value, video_id))


def search(embedding: list, top_k: int, scope: RetrievalScope | None = None) -> list:
    """余弦距离检索（<=>），返回 [{text, meta, distance}]。"""
    qvec = _vector_literal(embedding)
    where, params = scope_filter(scope)
    with _conn() as c:
        cur = c.execute(
            f"""
            SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                   COALESCE(ch.evidence_source, v.source), ch.chunk_idx, ch.embedding <=> %s::vector AS distance
            FROM chunks ch
            JOIN videos v ON v.video_id = ch.video_id
            WHERE {where}
            ORDER BY ch.embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, *params, qvec, top_k),
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


class VideoImportBusy(RuntimeError):
    """有导入正在持有该视频的锁。"""


def delete_video(video_id: str) -> bool:
    """仅删除已入库的视频，外键级联清除字幕、证据和向量。"""
    with _conn() as c:
        locked = c.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (video_id,)).fetchone()[0]
        if not locked:
            raise VideoImportBusy(video_id)
        return c.execute("""
            DELETE FROM videos v WHERE v.video_id = %s
            AND EXISTS (SELECT 1 FROM chunks ch WHERE ch.video_id = v.video_id)
            """, (video_id,)).rowcount == 1


# 混合检索参数
HYBRID_VEC_K = 50   # 向量通道候选数
HYBRID_BM_K = 50    # 全文通道候选数
RRF_K = 60          # RRF 常数


def _hits_from_rows(rows, lexical_keys=None) -> list:
    """把 (text,start,end,video_id,title,author,source,chunk_idx,distance) 行转成统一 hit 结构。

    lexical_keys: {(video_id, chunk_idx)}，命中该 key 的 hit 标记 lexical=True（被全文通道召回，
    距离阈值过滤时应豁免——关键词精确命中是强相关信号，即使向量距离偏大也保留）。"""
    out = []
    for text, start, end, vid, title, author, source, chunk_idx, distance, *details in rows:
        key = (vid, int(chunk_idx))
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
                **(dict(zip(("published_at", "stage_name"), details)) if details else {}),
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
            SELECT video_id, chunk_idx, start_sec, end_sec, text, evidence_source
            FROM chunks WHERE video_id = ANY(%s)
            ORDER BY video_id, chunk_idx
            """,
            (vids,),
        ).fetchall()
    book: dict = {}
    for vid, idx, s, e, t, source in rows:
        book.setdefault(vid, {})[int(idx)] = (float(s), float(e), t, source)

    out = []
    covered = set()  # 已被并入某条结果的 (video_id, chunk_idx)
    for h in hits:
        m = h["meta"]
        vid, idx = m["video_id"], m["chunk_idx"]
        if (vid, idx) in covered:
            continue
        chunks = book.get(vid, {})
        if idx not in chunks or chunks[idx][3] is not None:
            # 带独立来源和时间点的证据不与相邻字幕混合。
            out.append(h)
            continue
        idxs = [i for i in range(idx - window, idx + window + 1)
                if i in chunks and chunks[i][3] is None and (vid, i) not in covered]
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


def attribute_search(embedding, entity, evidence_pattern, game_id, scope=None, limit=6):
    """匹配同一句中的实体与属性；不依赖既有切片是怎样分词的。"""
    qvec = _vector_literal(embedding)
    where, params = scope_filter(scope)
    with _conn() as c:
        rows = c.execute(f"""
            SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                   COALESCE(ch.evidence_source, v.source), ch.chunk_idx,
                   ch.embedding <=> %s::vector AS distance, v.published_at, v.stage_name
            FROM chunks ch JOIN videos v ON v.video_id=ch.video_id
            WHERE {where} AND (v.game_id = %s OR v.game_id IS NULL)
              AND strpos(ch.text, %s) > 0
              AND EXISTS (SELECT 1 FROM regexp_split_to_table(ch.text, '[。！？!?；;\n]+') AS s(sentence)
                          WHERE strpos(s.sentence, %s) > 0 AND s.sentence ~ %s)
            ORDER BY distance, ch.id LIMIT %s
            """, (qvec, *params, game_id, entity, entity, evidence_pattern, limit)).fetchall()
    return _hits_from_rows(rows)


def hybrid_search(embedding: list, query_terms: str, top_k: int, scope: RetrievalScope | None = None,
                  trace=None) -> list:
    """混合检索：向量 top vec_k + 全文(top bm_k) 各自取候选，RRF 融合后取 top_k。

    query_terms: 空格分词串（由 tokenizer.query_terms 生成）。为空则退化为纯向量。
    返回与 search 同构的 [{text, meta, distance}]。
    """
    qvec = _vector_literal(embedding)
    where, params = scope_filter(scope)
    with _conn() as c:
        # 向量通道
        vec_rows = c.execute(
            f"""
            SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                   COALESCE(ch.evidence_source, v.source), ch.chunk_idx, ch.embedding <=> %s::vector AS distance, v.published_at, v.stage_name
            FROM chunks ch JOIN videos v ON v.video_id = ch.video_id
            WHERE {where}
            ORDER BY ch.embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, *params, qvec, HYBRID_VEC_K),
        ).fetchall()

        # 全文通道（simple 配置按空格分词，tokens 列已存空格分词）。
        # 用 AND 语义：只召回同时含多个查询信息词的 chunk，避免宽 OR 被高频词淹没。
        # 查询词过少（<2）或 AND 空结果时退化为纯向量（full_rows 空）。
        if query_terms.strip():
            qts = " & ".join(query_terms.split())
            full_rows = c.execute(
                f"""
                SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                       COALESCE(ch.evidence_source, v.source), ch.chunk_idx, ch.embedding <=> %s::vector AS distance, v.published_at, v.stage_name
                FROM chunks ch JOIN videos v ON v.video_id = ch.video_id
                WHERE {where} AND to_tsvector('simple', ch.tokens) @@ to_tsquery('simple', %s)
                ORDER BY ts_rank_cd(to_tsvector('simple', ch.tokens), to_tsquery('simple', %s)) DESC
                LIMIT %s
                """,
                (qvec, *params, qts, qts, HYBRID_BM_K),
            ).fetchall()
        else:
            full_rows = []

    # 同一时间戳的不同画面证据不可合并。
    agg = {}
    for rank, row in enumerate(vec_rows, 1):
        key = (row[3], int(row[7]))
        agg[key] = agg.get(key, 0.0) + 1.0 / (RRF_K + rank)
    lexical_keys = set()
    for rank, row in enumerate(full_rows, 1):
        key = (row[3], int(row[7]))
        agg[key] = agg.get(key, 0.0) + 1.0 / (RRF_K + rank)
        lexical_keys.add(key)

    merged = {key: row for key, row in
              [((r[3], int(r[7])), r) for r in vec_rows + full_rows]}
    top_keys = [k for k, _ in sorted(agg.items(), key=lambda x: -x[1])[:top_k]]
    if trace:
        def summarize(rows):
            return [{"video_id": row[3], "chunk_idx": int(row[7]), "start": row[1], "distance": float(row[8])}
                    for row in rows]
        trace("hybrid", scope=scope.model_dump() if scope else None,
              vector=summarize(vec_rows), lexical=summarize(full_rows), fused=top_keys)
    return _hits_from_rows([merged[k] for k in top_keys], lexical_keys)
