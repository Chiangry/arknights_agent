"""离线验证混合检索：向量(真实 bge-m3) + BM25(关键词) 双通道，RRF 融合。

目的：验证关键词通道能否救回"标准引擎"这类纯向量 miss，并对比整体 HitRate/MRR。
命中判定与 eval_rag.py 一致。与纯向量基线(400/50: 96.8%/0.874)对比。
用法: python scripts/eval/eval_hybrid.py
"""
import json
import math
import sys
from pathlib import Path

import jieba
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.chunker import build_chunks
from index.embedder import embed_texts

CACHE = Path(__file__).parent / "segments_cache.json"
QUESTIONS = Path(__file__).parent / "questions.json"

TARGET, OVERLAP = 400, 50  # 与当前生产切分一致
TOP_KV = 50          # 向量通道候选数
TOP_KB = 50          # BM25 通道候选数
RRF_K = 60           # RRF 常数

# 中文停用词：查询里无检索价值的虚词/疑问词
STOP = set("的了是有什么吗怎么呢么吧啊呀哦在就也还和与或个这那哪都都会要去能可以自己我们大家"
           "用看想知知道应该该应当需要哪些啥哪种哪一一个几种多少")


def tok(text):
    return [w for w in jieba.cut(text) if w.strip() and len(w) > 1 and w not in STOP]


def load():
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    texts, metas = [], []
    for vid, info in cache.items():
        segs = [tuple(s) for s in info["segments"]]
        for ch in build_chunks(segs, target=TARGET, overlap=OVERLAP):
            texts.append(ch["text"])
            metas.append({"video_id": vid, "start": ch["start"], "end": ch["end"]})
    return texts, metas, qs


def build_bm25(texts):
    """返回 (n_docs, doc_len, avgdl, df, postings)。postings[term] = [(doc_idx, tf), ...]"""
    n = len(texts)
    doc_len = [0] * n
    df = {}
    postings = {}
    for i, t in enumerate(texts):
        terms = tok(t)
        doc_len[i] = len(terms)
        seen = {}
        for w in terms:
            seen[w] = seen.get(w, 0) + 1
        for w, c in seen.items():
            postings.setdefault(w, []).append((i, c))
        for w in seen:
            df[w] = df.get(w, 0) + 1
    avgdl = sum(doc_len) / n
    return n, doc_len, avgdl, df, postings


def bm25_scores(q_terms, n, doc_len, avgdl, df, postings, top_k):
    k1, b = 1.5, 0.75
    scores = {}
    for w in q_terms:
        if w not in postings:
            continue
        idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
        for i, tf in postings[w]:
            dl = doc_len[i]
            s = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            scores[i] = scores.get(i, 0.0) + s
    return sorted(scores.items(), key=lambda x: -x[1])[:top_k]


def overlap(meta, gt):
    return meta["video_id"] == gt["video_id"] and \
        float(meta["start"]) < gt["end"] and float(meta["end"]) > gt["start"]


def rrf_fuse(vec_ranks, bm_ranks, top_k):
    """vec_ranks/bm_ranks: [(doc_idx, rank_1based), ...]"""
    agg = {}
    for lst in (vec_ranks, bm_ranks):
        for idx, rank in lst:
            agg[idx] = agg.get(idx, 0.0) + 1.0 / (RRF_K + rank)
    ranked = sorted(agg.items(), key=lambda x: -x[1])
    return [i for i, _ in ranked[:top_k]]


def main():
    texts, metas, qs = load()
    print(f"chunk数={len(texts)} | 测试集 {len(qs)} 条 | 阈值基线对照 400/50 纯向量", flush=True)
    mat = np.array(embed_texts(texts))
    norm = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
    matn = mat / norm

    n, doc_len, avgdl, df, postings = build_bm25(texts)

    vec_hit = vec_mrr = hy_hit = hy_mrr = 0.0
    for gt in qs:
        q_vec = np.asarray(embed_texts([gt["question"]])[0])
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-9)
        dists = 1.0 - (matn @ q_vec)
        vec_order = np.argsort(dists)[:TOP_KV]
        vec_ranks = [(int(i), r) for r, i in enumerate(vec_order, 1)]

        q_terms = tok(gt["question"])
        bm_list = bm25_scores(q_terms, n, doc_len, avgdl, df, postings, TOP_KB)
        bm_ranks = [(i, r) for r, (i, _) in enumerate(bm_list, 1)]

        # 纯向量 top5
        v_rk = next((r for r, i in enumerate(vec_order[:5], 1) if overlap(metas[i], gt)), None)
        # 混合 top5
        fused = rrf_fuse(vec_ranks, bm_ranks, 5)
        h_rk = next((r for r, i in enumerate(fused, 1) if overlap(metas[i], gt)), None)

        vec_hit += int(v_rk is not None)
        vec_mrr += 1.0 / v_rk if v_rk else 0
        hy_hit += int(h_rk is not None)
        hy_mrr += 1.0 / h_rk if h_rk else 0

        if "标准引擎" in gt["question"]:
            bm_top = [(metas[i]["video_id"], round(metas[i]["start"])) for i, _ in bm_list[:3]]
            print(f"\n>>> [标准引擎] 纯向量rank={v_rk} 混合rank={h_rk}")
            print(f"    BM25 命中前3: {bm_top}")

    nq = len(qs)
    print(f"\n{'通道':>12} {'HitRate@5':>10} {'MRR':>7}")
    print(f"{'纯向量':>12} {vec_hit/nq:>9.1%} {vec_mrr/nq:>7.3f}")
    print(f"{'混合(RRF)':>12} {hy_hit/nq:>9.1%} {hy_mrr/nq:>7.3f}")
    print(f"\n纯向量基线参考: 96.8% / 0.874")


if __name__ == "__main__":
    main()
