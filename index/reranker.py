"""Rerank：调用硅基流动 bge-reranker（cross-encoder）对候选片段重新打分。

- 输入：query + 候选文本列表
- 输出：与输入等长的相关度分数列表（0~1，越大越相关）；失败返回 None，由调用方回退。
"""
import config
import requests


def rerank_scores(query: str, documents: list) -> list | None:
    """返回 list[float]，长度=len(documents)；任何异常返回 None（触发回退）。"""
    if not documents or not config.RERANK_ENABLED:
        return None
    try:
        resp = requests.post(
            f"{config.SILICONFLOW_BASE_URL}/rerank",
            headers={"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"},
            json={
                "model": config.RERANK_MODEL,
                "query": query,
                "documents": documents,
            },
            timeout=config.RERANK_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        scores = [0.0] * len(documents)
        for it in results:
            idx = int(it["index"])
            if 0 <= idx < len(scores):
                scores[idx] = float(it["relevance_score"])
        return scores
    except Exception as e:  # 网络/鉴权/格式异常一律回退
        print(f"[rerank] 调用失败，回退混合检索: {type(e).__name__}: {e}")
        return None
