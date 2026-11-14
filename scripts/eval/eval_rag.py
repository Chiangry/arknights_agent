"""RAG 检索质量评测（生产库）：读测试集，逐条跑检索，输出 HitRate@k / MRR。

四视角：
  - 原始纯向量（search，top_k 内不设阈值）：索引 + embedding + 切分 的召回能力
  - 纯向量阈值过滤：SCORE_THRESHOLD 下的最终引用质量
  - 混合检索（向量 + 全文 RRF 融合 + 阈值）：上 rerank 前的生产路径
  - 混合 + rerank（生产 retrieve：放宽候选 → bge-reranker 精排 → 分数过滤）

命中判定：检索片段 与 ground truth 同 video_id 且时间区间有重叠。
用法：python scripts/eval/eval_rag.py [--top-k 5]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from index.embedder import embed_texts
from index.store import search, hybrid_search
from index.tokenizer import query_terms
from rag.retriever import retrieve as real_retrieve


def overlap(hit_meta, gt) -> bool:
    """命中：同视频 且 时间区间有重叠。"""
    if hit_meta["video_id"] != gt["video_id"]:
        return False
    return float(hit_meta["start"]) < gt["end"] and float(hit_meta["end"]) > gt["start"]


def first_rank(cands, gt):
    for i, h in enumerate(cands):
        if overlap(h["meta"], gt):
            return i + 1, h
    return None, None


def eval_one(question: str, gt: dict, top_k: int):
    emb = embed_texts([question])[0]
    raw = search(emb, top_k)
    vec_filt = [h for h in raw if h["distance"] <= config.SCORE_THRESHOLD]
    terms = query_terms(question)
    hyb = [h for h in hybrid_search(emb, terms, top_k)
           if h["distance"] <= config.SCORE_THRESHOLD or h.get("lexical")]

    raw_rank, raw_hit = first_rank(raw, gt)
    vf_rank, vf_hit = first_rank(vec_filt, gt)
    hy_rank, hy_hit = first_rank(hyb, gt)
    rr = real_retrieve(question, top_k)   # 真实生产路径（含 rerank）
    # rerank 严格命中：时间重叠 且 相关度分数达下限（避免"时间重叠但内容无关"的假命中）
    strict_rank, strict_hit = None, None
    for i, h in enumerate(rr):
        if overlap(h["meta"], gt) and h.get("rerank_score", 0.0) >= config.RERANK_MIN_SCORE:
            strict_rank, strict_hit = i + 1, h
            break
    rr_rank, rr_hit = first_rank(rr, gt)
    return {
        "question": question,
        "raw_rank": raw_rank,
        "vec_filtered_rank": vf_rank,
        "hybrid_rank": hy_rank,
        "rerank_rank": rr_rank,
        "rerank_strict_rank": strict_rank,
        "raw_hit_distance": raw_hit["distance"] if raw_hit else None,
        "hybrid_hit_distance": hy_hit["distance"] if hy_hit else None,
        "rerank_hit_score": rr_hit.get("rerank_score") if rr_hit else None,
        "raw_hit_text": raw_hit["text"][:60] if raw_hit else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=config.TOP_K)
    ap.add_argument("--questions", default=Path(__file__).parent / "questions.json")
    args = ap.parse_args()

    qs = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    print(f"测试集 {len(qs)} 条 | top_k={args.top_k} | 阈值={config.SCORE_THRESHOLD}\n")

    raw_hit = vec_hit = hy_hit = rr_hit = rr_strict = 0
    raw_mrr = vec_mrr = hy_mrr = rr_mrr = rr_strict_mrr = 0.0
    for gt in qs:
        r = eval_one(gt["question"], gt, args.top_k)
        rh, vh, hh, rr, rs = (x is not None for x in
                              (r["raw_rank"], r["vec_filtered_rank"], r["hybrid_rank"],
                               r["rerank_rank"], r["rerank_strict_rank"]))
        raw_hit += int(rh); vec_hit += int(vh); hy_hit += int(hh)
        rr_hit += int(rr); rr_strict += int(rs)
        raw_mrr += 1.0 / r["raw_rank"] if rh else 0.0
        vec_mrr += 1.0 / r["vec_filtered_rank"] if vh else 0.0
        hy_mrr += 1.0 / r["hybrid_rank"] if hh else 0.0
        rr_mrr += 1.0 / r["rerank_rank"] if rr else 0.0
        rr_strict_mrr += 1.0 / r["rerank_strict_rank"] if rs else 0.0

        mark = "✅" if rs else ("⚠️" if (rh or vh or hh) else "❌")
        d = f"{r['raw_hit_distance']:.3f}" if r["raw_hit_distance"] else "-"
        sc = f"{r['rerank_hit_score']:.3f}" if r.get("rerank_hit_score") is not None else "-"
        print(
            f"{mark} [{gt['video_id']} {gt['start']}s-{gt['end']}s] "
            f"向量rank={r['raw_rank']} 向量过滤={r['vec_filtered_rank']} "
            f"混合rank={r['hybrid_rank']} rerank={r['rerank_rank']}(score={sc}) "
            f"严格={r['rerank_strict_rank']} dist={d}"
        )
        print(f"     Q: {gt['question']}")

    n = len(qs)
    print("\n===== 汇总 =====")
    print(f"纯向量(原始)     HitRate@{args.top_k}={raw_hit}/{n}={raw_hit/n:.2%}   MRR={raw_mrr/n:.3f}")
    print(f"纯向量(阈值过滤) HitRate@{args.top_k}={vec_hit}/{n}={vec_hit/n:.2%}   MRR={vec_mrr/n:.3f}")
    print(f"混合(上rerank前) HitRate@{args.top_k}={hy_hit}/{n}={hy_hit/n:.2%}   MRR={hy_mrr/n:.3f}")
    print(f"混合+rerank(重叠判) HitRate@{args.top_k}={rr_hit}/{n}={rr_hit/n:.2%}   MRR={rr_mrr/n:.3f}")
    print(f"混合+rerank(严格:重叠+分数达标) HitRate@{args.top_k}={rr_strict}/{n}={rr_strict/n:.2%}   MRR={rr_strict_mrr/n:.3f}")
    print(f"说明：rerank 开关={config.RERANK_ENABLED} 候选数={config.RERANK_CANDIDATES} "
          f"分数下限={config.RERANK_MIN_SCORE}")


if __name__ == "__main__":
    main()
