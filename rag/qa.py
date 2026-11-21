"""问答：把检索到的片段拼进上下文，交给 DeepSeek 生成回答。"""
import config
from openai import OpenAI
from rag.retriever import retrieve
from text_normalization import to_simplified

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
        )
    return _client


def ask(question: str, top_k: int | None = None) -> tuple:
    """
    返回 (answer, hits)。answer 为 DeepSeek 生成结果，
    hits 为检索命中的片段（含时间戳），供展示与校验。
    """
    hits = retrieve(question, top_k)

    ctx = []
    for i, h in enumerate(hits, 1):
        ctx.append(
            f"[片段{i}] 时间段 {h['meta']['start']:.0f}s-{h['meta']['end']:.0f}s\n{h['text']}"
        )
    context = "\n\n".join(ctx)

    system = (
        "你是视频知识库问答助手。根据下面提供的视频片段回答用户的问题。"
        "默认使用简体中文。回答要准确、忠于片段内容，并在关键信息后标注来源时间段（如 [12s-45s]）。"
        "如果片段中没有答案，明确说明'片段中未找到相关信息'，不要编造。"
    )
    user = f"视频片段：\n{context}\n\n问题：{question}"

    resp = get_client().chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    answer = to_simplified(resp.choices[0].message.content or "")
    return answer, hits
