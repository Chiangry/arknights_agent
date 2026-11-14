"""文本切分：把带时间戳的转写片段拼成适合检索的 chunk，保留起止时间。

两套策略：
- build_chunks         固定字符窗口 + 字符 overlap（baseline，参数敏感）
- build_semantic_chunks 语义优先：chunk 边界尽量落在完整句子结束处，避免切开关键句
"""
from config import CHUNK_TARGET_CHARS, CHUNK_OVERLAP_CHARS

# 句子强结束符：命中才把当前 buffer 断成一个 chunk
_END_MARKS = ("。", "！", "？", "…", "!", "?", ".", "…", "；", ";")
# 语义切分参数（单位：字符）。min 开始寻找切点，max 强制切，避免 chunk 无限长。
SEMANTIC_MIN = 360
SEMANTIC_MAX = 720


def build_chunks(
    segments: list,
    target: int = CHUNK_TARGET_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list:
    """
    segments: [(start, end, text)]
    返回: [{"text": str, "start": float, "end": float}, ...]
    策略：按字符数累积成 chunk，达到 target 就截断，并保留尾部若干字符作为
    与下一段的重叠，避免检索时把关键句切在两段中间。
    """
    chunks = []
    buffer = []   # 当前累积的片段
    buf_len = 0

    for start, end, text in segments:
        buffer.append((start, end, text))
        buf_len += len(text)
        if buf_len >= target:
            chunk_start = buffer[0][0]
            chunk_end = buffer[-1][1]
            chunk_text = " ".join(t for _, _, t in buffer)
            chunks.append({"text": chunk_text, "start": chunk_start, "end": chunk_end})

            # 保留尾部片段作为重叠
            keep, keep_len = [], 0
            for s, e, t in reversed(buffer):
                keep.insert(0, (s, e, t))
                keep_len += len(t)
                if keep_len >= overlap:
                    break
            buffer, buf_len = keep, keep_len

    if buffer:
        chunks.append({
            "text": " ".join(t for _, _, t in buffer),
            "start": buffer[0][0],
            "end": buffer[-1][1],
        })
    return chunks


def build_semantic_chunks(
    segments: list,
    min_target: int = SEMANTIC_MIN,
    max_target: int = SEMANTIC_MAX,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list:
    """语义优先切分：累积到 min_target 后，遇到句子结束符才切 chunk；
    达到 max_target 仍未结束则强制在条目边界切。避免把完整观点切到两段中间。"""
    chunks = []
    buffer = []
    buf_len = 0

    def flush():
        nonlocal buffer, buf_len
        if not buffer:
            return
        chunks.append({
            "text": " ".join(t for _, _, t in buffer),
            "start": buffer[0][0],
            "end": buffer[-1][1],
        })
        keep, keep_len = [], 0
        for s, e, t in reversed(buffer):
            keep.insert(0, (s, e, t))
            keep_len += len(t)
            if keep_len >= overlap:
                break
        buffer, buf_len = keep, keep_len

    for start, end, text in segments:
        buffer.append((start, end, text))
        buf_len += len(text)
        last = text.rstrip()
        is_end = last.endswith(_END_MARKS)
        if buf_len >= min_target and is_end:
            flush()
        elif buf_len >= max_target:
            flush()

    if buffer:
        chunks.append({
            "text": " ".join(t for _, _, t in buffer),
            "start": buffer[0][0],
            "end": buffer[-1][1],
        })
    return chunks
