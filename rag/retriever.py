"""检索：混合召回（向量 + 全文 RRF）→ bge-reranker 二次精排 → 分数过滤取 top_k。

rerank 关闭或调用失败时，回退到原混合检索的阈值过滤逻辑。
"""
from itertools import zip_longest

import config
from index.catalog import RetrievalScope
from index.embedder import embed_texts
from index.reranker import rerank_scores
from index.store import attribute_search, expand_neighbors, hybrid_search
from index.tokenizer import query_terms
from rag.video_retrieval import source_context
from rag.query_signals import query_signals
from text_normalization import to_simplified


def _fallback_filter(hits: list, top_k: int) -> list:
    """原混合检索过滤：dist<=阈值 或 关键词精确命中(lexical) 豁免。"""
    return [h for h in hits
            if h["distance"] <= config.SCORE_THRESHOLD or h.get("lexical")][:top_k]


def _truncate(text: str, limit: int = 700) -> str:
    """rerank 输入控制长度（cross-encoder 512 token 上限，中文约 1 字≈1 token）。"""
    return text if len(text) <= limit else text[:limit]


def _key(hit):
    return hit["meta"]["video_id"], hit["meta"]["chunk_idx"]


def _summary(hit):
    vid, idx = _key(hit)
    return {"video_id": vid, "chunk_idx": idx, "start": hit["meta"].get("start"),
            "distance": hit.get("distance"), "lexical": hit.get("lexical", False),
            "attribute_match": hit.get("attribute_match"), "rerank_score": hit.get("rerank_score")}


def _prioritize_evidence(hits, top_k):
    # 最多两个属性候选优先，剩余位置保持原来的顺序。
    preferred = [hit for hit in hits if hit.get("attribute_match")][:2]
    keys = {_key(hit) for hit in preferred}
    return (preferred + [hit for hit in hits if _key(hit) not in keys])[:top_k]


def retrieve(question: str, top_k: int | None = None, scope: RetrievalScope | None = None,
             video_hints: tuple[str, ...] = (), ranking_question: str | None = None, trace=None) -> list:
    top_k = top_k or config.TOP_K
    question = to_simplified(question)
    signals = query_signals(question, scope)
    expanded = signals.expand(question) if signals else question
    ranking_query = to_simplified(ranking_question) if ranking_question else question
    if signals:
        ranking_query = signals.expand(ranking_query)
    terms = query_terms(question)
    if trace:
        trace("query", question=question, embedding_query=expanded, ranking_query=ranking_query,
              lexical_terms=terms, entity=signals.entity if signals else None,
              attribute=signals.attribute if signals else None, video_hints=video_hints)
    emb = embed_texts([expanded])[0]

    # 1) 放宽候选：rerank 开启时取更多候选（不卡距离阈值，保证召回）
    cand_k = max(top_k, config.RERANK_CANDIDATES) if config.RERANK_ENABLED else top_k
    trace_args = {"trace": trace} if trace else {}
    hits = hybrid_search(emb, terms, cand_k, scope=scope, **trace_args)
    if video_hints:
        base = scope or RetrievalScope()
        ids = [vid for vid in video_hints if not base.video_ids or vid in base.video_ids]
        if ids:
            hint_scope = base.model_copy(update={"video_ids": ids})
            focused = hybrid_search(emb, terms, min(8, cand_k), scope=hint_scope, **trace_args)
            # 候选专用通道，不给标题命中词法豁免；内容仍须通过既有精排/阈值。
            merged = {}
            for pair in zip_longest(hits, focused):
                for hit in pair:
                    if hit is not None:
                        meta = hit["meta"]
                        merged.setdefault((meta["video_id"], meta["chunk_idx"]), hit)
            hits = list(merged.values())
    if signals:
        matches = attribute_search(emb, signals.entity, signals.evidence_pattern, signals.game_id, scope=scope)
        if trace:
            trace("attribute", candidates=[_summary(hit) for hit in matches])
        merged = {_key(hit): hit for hit in hits}
        for match in matches:
            hit = merged.setdefault(_key(match), match)
            hit["attribute_match"] = signals.attribute
        hits = list(merged.values())
    if not hits:
        if trace:
            trace("final_hits", hits=[])
        return []

    # 2) rerank 二次精排
    kept = None
    ranked = hits
    reranked = False
    if config.RERANK_ENABLED:
        scores = rerank_scores(ranking_query, [
            _truncate(f"{source_context(h)[:200]}\n{h['meta'].get('source') or '片段'}：{h['text']}") for h in hits
        ])
        if scores is not None:
            for h, s in zip(hits, scores):
                h["rerank_score"] = s
            ranked = sorted(hits, key=lambda h: -h["rerank_score"])
            reranked = True
            kept = [h for h in ranked if h["rerank_score"] >= config.RERANK_MIN_SCORE]
    if kept is None:
        kept = _fallback_filter(hits, len(hits))
    selected = _prioritize_evidence(kept, top_k)
    if trace:
        eligible, selected_keys = {_key(h) for h in kept}, {_key(h) for h in selected}
        trace("ranking", mode="rerank" if reranked else "fallback" if config.RERANK_ENABLED else "distance",
              threshold=config.RERANK_MIN_SCORE if reranked else config.SCORE_THRESHOLD,
              candidates=[{**_summary(h), "decision": "selected" if _key(h) in selected_keys else
                           "top_k" if _key(h) in eligible else "below_threshold"} for h in ranked])
    final = expand_neighbors(selected, config.NEIGHBOR_WINDOW)
    if trace:
        trace("final_hits", hits=[_summary(h) for h in final])
    return final


def retrieve_with_status(question: str, top_k: int | None = None, scope: RetrievalScope | None = None,
                         video_hints: tuple[str, ...] = (), ranking_question: str | None = None,
                         trace=None) -> tuple[list, str, str]:
    """检索并给 Agent 一个可解释的证据状态。

    ``sufficient`` 代表可以回答；``insufficient`` 代表不应仅凭本地片段回答，
    由上层决定是否调用外部搜索工具。这里不触发网络请求，保持检索层可测试。
    """
    hits = retrieve(question, top_k, scope=scope, video_hints=video_hints, ranking_question=ranking_question, trace=trace)
    if not hits:
        return [], "insufficient", "知识库未检索到相关片段"

    score = max((float(h["rerank_score"]) for h in hits if "rerank_score" in h), default=None)
    if score is not None:
        if score < config.EXTERNAL_SEARCH_RERANK_THRESHOLD:
            return hits, "insufficient", (
                f"本地片段相关度不足（最高 rerank 分 {score:.3f}）"
            )
        return hits, "sufficient", f"本地检索命中 {len(hits)} 个相关片段"

    # rerank 不可用时，retrieve 已执行距离阈值过滤；不额外拒绝有效命中。
    return hits, "sufficient", f"本地检索命中 {len(hits)} 个相关片段"
