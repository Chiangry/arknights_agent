"""单问题检索诊断：把一次问答的检索拆成 4 层打印，定位"没有找到"的原因。

用法: python scripts/diagnose_query.py "卫戍协议是一个什么模式？"

四层：
  1) 分词（query_terms）—— 看清哪些词进入全文通道
  2) 向量通道 top10 —— 距离多少、正确片段排第几
  3) 全文通道 top10 —— 关键词是否命中（空 = 正文里根本没有这些词）
  4) 混合 RRF 融合 + 阈值过滤 —— 最终进 LLM 的引用
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import index.store as store
from index.embedder import embed_texts
from index.tokenizer import query_terms

VEC_LIMIT = 10
FULL_LIMIT = 10


def _rows_to_lines(rows, show_lexical=False):
    out = []
    for i, r in enumerate(rows, 1):
        text, start, end, vid, title, author, source, dist = r
        out.append(
            f"    #{i} {vid} [{start:.0f}s-{end:.0f}s] dist={dist:.3f} "
            f"| {text[:34].replace(chr(10), ' ')}"
        )
    return out


def diagnose(q: str):
    emb = embed_texts([q])[0]
    terms = query_terms(q)
    qvec = store._vector_literal(emb)

    print(f"\n问题: {q}")
    print(f"【1】全文分词 query_terms: {terms!r}   (空格分隔串 → 用于 to_tsquery '&')")

    with store._conn() as c:
        vec_rows = c.execute(
            """
            SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                   v.source, ch.embedding <=> %s::vector AS distance
            FROM chunks ch JOIN videos v ON v.video_id = ch.video_id
            ORDER BY ch.embedding <=> %s::vector LIMIT %s
            """, (qvec, qvec, VEC_LIMIT)).fetchall()

        full_rows = []
        qts = " & ".join(terms.split()) if terms.strip() else ""
        if qts:
            full_rows = c.execute(
                """
                SELECT ch.text, ch.start_sec, ch.end_sec, v.video_id, v.title, v.author,
                       v.source, ch.embedding <=> %s::vector AS distance
                FROM chunks ch JOIN videos v ON v.video_id = ch.video_id
                WHERE to_tsvector('simple', ch.tokens) @@ to_tsquery('simple', %s)
                ORDER BY ts_rank_cd(to_tsvector('simple', ch.tokens),
                                    to_tsquery('simple', %s)) DESC LIMIT %s
                """, (qvec, qts, qts, FULL_LIMIT)).fetchall()

    print(f"【2】向量通道 top{VEC_LIMIT}:")
    print("\n".join(_rows_to_lines(vec_rows)) if vec_rows else "    (空)")

    print(f"【3】全文通道 top{FULL_LIMIT}  (tsquery: {qts!r}):")
    if not qts:
        print("    查询词为空 → 全文通道禁用（退化为纯向量）")
    elif not full_rows:
        print("    ⚠️ 违规：正文 token 里没有任何 chunk 同时含全部查询词 → 全文通道无命中")
    else:
        print("\n".join(_rows_to_lines(full_rows)))

    # 4) 混合融合 + 阈值
    hits = store.hybrid_search(emb, terms, config.TOP_K)
    print(f"【4】混合 RRF 融合（top_k={config.TOP_K}）+ 阈值过滤(dist<={config.SCORE_THRESHOLD} 或 lexical):")
    kept = [h for h in hits if h["distance"] <= config.SCORE_THRESHOLD or h.get("lexical")]
    for i, h in enumerate(hits, 1):
        m = h["meta"]
        tag = "保留" if (h["distance"] <= config.SCORE_THRESHOLD or h.get("lexical")) else "丢弃"
        lex = "lexical✓ " if h.get("lexical") else ""
        print(f"    #{i} {tag} {lex}{m['video_id']} [{m['start']:.0f}s] "
              f"dist={h['distance']:.3f} | {h['text'][:30].replace(chr(10), ' ')}")
    print(f"  => 最终进入 LLM 的引用数: {len(kept)}", "（→ '没有找到回答'）" if not kept else "")

    # 附加：标题里是否含关键词（诊断标题未入索引问题）
    print("\n【附加】各视频标题（检查关键词是否只在标题里有）:")
    with store._conn() as c:
        titles = c.execute("SELECT video_id, title FROM videos ORDER BY video_id").fetchall()
    for vid, title in titles:
        mark = " ← 含查询词" if any(t in title for t in terms.split()) else ""
        print(f"    {vid}  {title}{mark}")


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "卫戍协议是一个什么模式？"
    diagnose(q)
