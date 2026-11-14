"""向量化：通过硅基流动 OpenAI 兼容接口调用 bge-m3 生成 embedding。"""
import config
from openai import OpenAI

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.SILICONFLOW_API_KEY,
            base_url=config.SILICONFLOW_BASE_URL,
        )
    return _client


def embed_texts(texts: list) -> list:
    """批量向量化，返回 list[list[float]]，顺序与输入一致。"""
    if not texts:
        return []
    client = get_client()
    resp = client.embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    # 按输入顺序排列
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in ordered]
