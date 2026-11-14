"""rerank 试点：对代表性问题，展示 改前(混合RRF排序) vs 改后(bge-reranker重排) 的差异。

离线重建 400/50 chunk + bge-m3 候选（与 eval_hybrid 一致），rerank 用硅基 bge-reranker-v2-m3。
用法: python scripts/eval/pilot_rerank.py
"""
import json
import math
import sys
from pathlib import Path

import jieba
import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from ingest.chunker import build_chunks
from index.embedder import embed_texts

CACHE = Path(__file__).parent / "segments_cache.json"
QUESTIONS = Path(__file__).parent / "questions.json"
TARGET, OVERLAP = 400, 50
RRF_K = 60
STOP = set("""什么 怎么 怎么样 如何 为何 为啥 为什么 多少 几个 几种 哪些 哪个 哪 这 那 这里 那里
这个 那个 一种 一点 一些 一下 一步 的 了 是 有 没 吗 呢 么 吧 啊 呀 哦 在 就 也 还 和 与 或
个 都 会 要 去 能 可以 自己 我们 你们 他们 大家 他 她 它 用 看 想 知道 应该 该 应当 需要 请 帮
我 讲 给 说明 事情 区别 作用 好处 干嘛 有关 关于 因为 所以 但是 还是 然后""".split())


def cut(t):
    return [w for w in jieba.cut(t) if w.strip() and len(w) > 1 and w not in STOP]


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
    n = len(texts); doc_len = [0] * n; df = {}; post = {}
    for i, t in enumerate(texts):
        seen = {}
        for w in cut(t):
            seen[w] = seen.get(w, 0) + 1
        doc_len[i] = len(seen)
        for w in seen:
            post.setdefault(w, []).append((i, seen[w]))
            df[w] = df.get(w, 0) + 1
    return n, doc_len, sum(doc_len) / n, df, post


def bm25_scores(qt, n, dl, avgdl, df, post, topk):
    k1, b = 1.5, 0.75; s = {}
    for w in qt:
        if w not in post:
            continue
        idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
        for i, tf in post[w]:
            s[i] = s.get(i, 0.0) + idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl[i] / avgdl))
    return sorted(s.items(), key=lambda x: -x[1])[:topk]


def rrf_fuse(vr, br, k=15):
    agg = {}
    for lst in (vr, br):
        for i, r in lst:
            agg[i] = agg.get(i, 0.0) + 1.0 / (RRF_K + r)
    return sorted(agg.items(), key=lambda x: -x[1])[:k]


def rerank(query, docs):
    r = requests.post(f"{config.SILICONFLOW_BASE_URL}/rerank",
                      headers={"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"},
                      json={"model": "BAAI/bge-reranker-v2-m3", "query": query, "documents": docs},
                      timeout=60)
    r.raise_for_status()
    by_idx = {it["index"]: it["relevance_score"] for it in r.json()["results"]}
    return by_idx


def overlap(m, gt):
    return m["video_id"] == gt["video_id"] and float(m["start"]) < gt["end"] and float(m["end"]) > gt["start"]


def show(texts, metas, gt, q, vec_order, bm_list):
    fused = rrf_fuse([(int(i), r) for r, i in enumerate(vec_order, 1)],
                     [(i, r) for r, (i, _) in enumerate(bm_list, 1)])
    cur_docs = [texts[i] for i, _ in fused[:15]]
    scores = rerank(q, cur_docs)
    print(f"\n### Q: {q}")
    print(f"  ground truth: {gt['video_id']} [{gt['start']}s-{gt['end']}s]")
    # 改前
    print("  [改前] 混合RRF top8:")
    for rk, (i, _) in enumerate(fused[:8], 1):
        m = metas[i]; hit = "✓" if overlap(m, gt) else " "
        print(f"    #{rk} {hit} {m['video_id']} [{m['start']:.0f}s] dist={1 - vec_order2cos[i]:.3f} {texts[i][:28]}")
    # 改后
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    print(f"  [改后] bge-reranker 重排 top8:")
    for rk, (pos, sc) in enumerate(ranked[:8], 1):
        i = fused[pos][0]; m = metas[i]; hit = "✓" if overlap(m, gt) else " "
        print(f"    #{rk} {hit} {m['video_id']} [{m['start']:.0f}s] score={sc:.4f} {texts[i][:28]}")
    # 命中 rank
    def first_rank(order):
        for r, p in enumerate(order, 1):
            if overlap(metas[fused[p][0]], gt):
                return r
        return None
    cur_rank = first_rank(range(len(fused)))
    new_rank = first_rank([p for p, _ in sorted(scores.items(), key=lambda x: -x[1])])
    print(f"  => 命中rank: 改前={cur_rank}  改后={new_rank}")


def main():
    texts, metas, qs = load()
    mat = np.array(embed_texts(texts)); matn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    n, dl, avgdl, df, post = build_bm25(texts)
    picks = ["游戏开发为什么没法一下子做出来？", "标准引擎有什么用？", "板藤应该在什么时候出售？", "卫戍协议是一个什么模式？"]
    for q in picks:
        gt = next((g for g in qs if g["question"] == q), None)
        if not gt:
            print(f"\n未找到问题: {q}"); continue
        qv = np.asarray(embed_texts([q])[0]); qv = qv / (np.linalg.norm(qv) + 1e-9)
        dist = 1.0 - (matn @ qv)
        vec_order = np.argsort(dist)
        bm_list = bm25_scores(cut(q), n, dl, avgdl, df, post, 15)
        global vec_order2cos
        vec_order2cos = {int(i): dist[i] for i in range(len(dist))}
        show(texts, metas, gt, q, vec_order, bm_list)


if __name__ == "__main__":
    main()
