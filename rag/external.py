"""B 站候选视频的请求内字幕检索。"""
from concurrent.futures import ThreadPoolExecutor
from math import sqrt

import config
from index.embedder import embed_texts
from index.reranker import rerank_scores
from ingest.bili_fetcher import fetch_subtitles
from ingest.chunker import build_chunks
from text_normalization import to_simplified


def _subtitle_chunks(video: dict) -> list[dict]:
    try:
        segments, source, title, author = fetch_subtitles(video["bvid"])
        return external_chunks(video, segments or [], source, title, author)
    except Exception:
        # 单个视频无法获取字幕时，继续使用其他候选。
        return []


def external_chunks(video: dict, segments: list, source: str, title=None, author=None) -> list[dict]:
    chunks = build_chunks(segments)
    if len(chunks) > 120:
        chunks = [chunks[i * (len(chunks) - 1) // 119] for i in range(120)]
    return [
        {
            "text": chunk["text"],
            "meta": {
                "video_id": video["bvid"],
                "title": title or video["title"],
                "author": author or video.get("author"),
                "start": chunk["start"],
                "end": chunk["end"],
                "source": source,
                "external": True,
            },
        }
        for chunk in chunks
    ]


def _cosine(a: list, b: list) -> float:
    norm = sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / norm if norm else 0.0


def retrieve_external(query: str, videos: list[dict]) -> tuple[list[dict], int]:
    """按排名检查至多五个候选，使用前三份可读字幕进行内存检索。"""
    candidates = []
    seen = set()
    for video in videos:
        if video["bvid"] not in seen:
            candidates.append(video)
            seen.add(video["bvid"])
        if len(candidates) == 5:
            break
    if not candidates:
        return [], 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        groups = [group for group in pool.map(_subtitle_chunks, candidates[:3]) if group]
        if len(groups) < 3:
            groups.extend(group for group in pool.map(_subtitle_chunks, candidates[3:]) if group)
    groups = groups[:3]
    chunks = [chunk for group in groups for chunk in group]
    return rank_external(query, chunks), len(groups)


def rank_external(query: str, chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []

    query = to_simplified(query)
    [query_vector] = embed_texts([query])
    ranked = []
    for start in range(0, len(chunks), 32):
        batch = chunks[start:start + 32]
        vectors = embed_texts([hit["text"] for hit in batch])
        ranked.extend((_cosine(query_vector, vector), hit)
                      for vector, hit in zip(vectors, batch, strict=True))
    ranked.sort(key=lambda item: item[0], reverse=True)
    shortlist = [hit for _, hit in ranked[:max(5, config.RERANK_CANDIDATES)]]
    scores = rerank_scores(query, [hit["text"][:700] for hit in shortlist])
    if scores is not None:
        scored = sorted(zip(scores, shortlist, strict=True), key=lambda pair: pair[0], reverse=True)
        shortlist = [hit for score, hit in scored if score >= config.RERANK_MIN_SCORE]
    return shortlist[:5]
