"""切分参数离线实验：不碰数据库，用不同 target/overlap 切分并对比检索质量。

流程：读 segments_cache -> 参数切分 -> 批量 embedding -> numpy 余弦检索 -> 对测试集算 HitRate/MRR。
命中判定与 eval_rag.py 一致（同视频 + 时间区间重叠），保证可对比。
用法：
  单点验证（对比真实库基线）:  python scripts/eval/eval_chunking.py --single 400 50
  参数扫描:                   python scripts/eval/eval_chunking.py
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.chunker import build_chunks, build_semantic_chunks
from index.embedder import embed_texts

CACHE = Path(__file__).parent / "segments_cache.json"
QUESTIONS = Path(__file__).parent / "questions.json"

# 参数网格：target(字符) x overlap(字符)
GRID = [(300, 50), (400, 0), (400, 50), (400, 100), (400, 150), (400, 200), (450, 50), (500, 50)]


def load_cache():
    return json.loads(CACHE.read_text(encoding="utf-8"))


def make_library(cache, target, overlap, semantic=False):
    """切分所有视频，返回 (texts, metas) 平铺列表；metas 含 video_id/start/end。"""
    texts, metas = [], []
    for vid, info in cache.items():
        segs = [tuple(s) for s in info["segments"]]  # (start, end, text)
        if semantic:
            chunks = build_semantic_chunks(segs, min_target=target, overlap=overlap)
        else:
            chunks = build_chunks(segs, target=target, overlap=overlap)
        for ch in chunks:
            texts.append(ch["text"])
            metas.append({"video_id": vid, "start": ch["start"], "end": ch["end"]})
    return texts, metas


def cosine_search(q_vec, mat, top_k):
    """q_vec: (1024,), mat: (N,1024)。返回按余弦距离升序的索引。距离 = 1 - cos，与 pgvector <=> 一致。"""
    q = np.asarray(q_vec)
    qn = q / (np.linalg.norm(q) + 1e-9)
    norm = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
    sims = (mat / norm) @ qn
    dists = 1.0 - sims
    return np.argsort(dists)[:top_k], dists


def overlap(hit_meta, gt):
    return hit_meta["video_id"] == gt["video_id"] and \
        float(hit_meta["start"]) < gt["end"] and float(hit_meta["end"]) > gt["start"]


def run(cache, questions, target, overlap_chars, top_k, verbose=True, semantic=False):
    texts, metas = make_library(cache, target, overlap_chars, semantic=semantic)
    tag = "语义" if semantic else f"窗口"
    print(f"  [{tag} target={target} overlap={overlap_chars}] chunk总数={len(texts)}", flush=True)
    if verbose and len(texts) == 0:
        return None

    mat = np.array(embed_texts(texts))  # (N,1024)
    hit = mrr = 0.0
    for gt in questions:
        q_vec = embed_texts([gt["question"]])[0]
        idxs, dists = cosine_search(q_vec, mat, top_k)
        rank = None
        for i, idx in enumerate(idxs, 1):
            if overlap(metas[idx], gt):
                rank = i
                break
        if rank:
            hit += 1
            mrr += 1.0 / rank
    n = len(questions)
    return {"chunks": len(texts), "hit": hit, "n": n,
            "hitrate": hit / n, "mrr": mrr / n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--single", nargs=2, type=int, metavar=("TARGET", "OVERLAP"))
    args = ap.parse_args()

    cache = load_cache()
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))

    if args.single:
        target, overlap = args.single
        r = run(cache, questions, target, overlap, args.top_k)
        print(f"\ntarget={target} overlap={overlap}: HitRate@{args.top_k}={r['hitrate']:.2%} MRR={r['mrr']:.3f}")
        return

    print(f"切分策略对比 | 测试集 {len(questions)} 条 | top_k={args.top_k}")
    print(f"{'策略':>8} {'target':>6} {'overlap':>7} {'chunks':>7} {'HitRate':>9} {'MRR':>7}")
    # 语义切分：min_target 由 target 控制
    for target, overlap in [(400, 50)]:
        r = run(cache, questions, target, overlap, args.top_k, verbose=False, semantic=True)
        if r:
            print(f"{'语义':>8} {target:>6} {overlap:>7} {r['chunks']:>7} {r['hitrate']:>8.1%} {r['mrr']:>7.3f}")
    # 固定窗口：当前线上参数 400/50 作对比
    for target, overlap in [(400, 50), (400, 100)]:
        r = run(cache, questions, target, overlap, args.top_k, verbose=False)
        if r:
            print(f"{'窗口':>8} {target:>6} {overlap:>7} {r['chunks']:>7} {r['hitrate']:>8.1%} {r['mrr']:>7.3f}")


if __name__ == "__main__":
    main()
