"""检索：混合召回（向量 + 全文 RRF）→ bge-reranker 二次精排 → 分数过滤取 top_k。

rerank 关闭或调用失败时，回退到原混合检索的阈值过滤逻辑。
"""
import config
from index.embedder import embed_texts
from index.reranker import rerank_scores
from index.store import expand_neighbors, hybrid_search
from index.tokenizer import query_terms


def _fallback_filter(hits: list, top_k: int) -> list:
    """原混合检索过滤：dist<=阈值 或 关键词精确命中(lexical) 豁免。"""
    return [h for h in hits
            if h["distance"] <= config.SCORE_THRESHOLD or h.get("lexical")][:top_k]


def _truncate(text: str, limit: int = 700) -> str:
    """rerank 输入控制长度（cross-encoder 512 token 上限，中文约 1 字≈1 token）。"""
    return text if len(text) <= limit else text[:limit]


def retrieve(question: str, top_k: int | None = None) -> list:
    top_k = top_k or config.TOP_K
    emb = embed_texts([question])[0]
    terms = query_terms(question)

    # 1) 放宽候选：rerank 开启时取更多候选（不卡距离阈值，保证召回）
    cand_k = max(top_k, config.RERANK_CANDIDATES) if config.RERANK_ENABLED else top_k
    hits = hybrid_search(emb, terms, cand_k)
    if not hits:
        return []

    # 2) rerank 二次精排
    if config.RERANK_ENABLED:
        scores = rerank_scores(question, [_truncate(h["text"]) for h in hits])
        if scores is not None:
            for h, s in zip(hits, scores):
                h["rerank_score"] = s
            ranked = sorted(hits, key=lambda h: -h["rerank_score"])
            # 分数达下限的才作引用；全低于下限时返回空（诚实"未找到"），不硬塞无关片段。
            kept = [h for h in ranked if h["rerank_score"] >= config.RERANK_MIN_SCORE][:top_k]
            # 相邻扩展：字幕固定窗口切分常把一段操作切在两个片段中间，只召回半截
            # 会让回答断在句中。这里把命中片段前后的相邻片段一并带上。
            return expand_neighbors(kept, config.NEIGHBOR_WINDOW)

    # 3) 回退：原阈值过滤
    return expand_neighbors(_fallback_filter(hits, top_k), config.NEIGHBOR_WINDOW)


def retrieve_with_status(question: str, top_k: int | None = None) -> tuple[list, str, str]:
    """检索并给 Agent 一个可解释的证据状态。

    ``sufficient`` 代表可以回答；``insufficient`` 代表不应仅凭本地片段回答，
    由上层决定是否调用外部搜索工具。这里不触发网络请求，保持检索层可测试。
    """
    hits = retrieve(question, top_k)
    if not hits:
        return [], "insufficient", "知识库未检索到相关片段"

    best = hits[0]
    if "rerank_score" in best:
        score = float(best["rerank_score"])
        if score < config.EXTERNAL_SEARCH_RERANK_THRESHOLD:
            return hits, "insufficient", (
                f"本地片段相关度不足（最高 rerank 分 {score:.3f}）"
            )
        return hits, "sufficient", f"本地检索命中 {len(hits)} 个相关片段"

    # rerank 不可用时，retrieve 已执行距离阈值过滤；不额外拒绝有效命中。
    return hits, "sufficient", f"本地检索命中 {len(hits)} 个相关片段"
