"""视频档案用于定位候选，字幕仍是攻略内容的证据。"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from index.catalog import RetrievalScope
from index.store import retrieval_video_catalog
from index.tokenizer import query_terms


@dataclass(frozen=True)
class VideoPlan:
    scope: RetrievalScope | None
    query: str
    hints: tuple[str, ...] = ()
    label: str = ""
    count: int = 0
    blocked: bool = False
    authors: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()
    published: tuple[int, int | None] | None = None

    def allows_external(self, video: dict) -> bool:
        if self.authors and (video.get("author") or "").strip().casefold() not in self.authors:
            return False
        if self.titles and (video.get("title") or "").strip().casefold() not in self.titles:
            return False
        if self.published:
            try:
                published = datetime.fromtimestamp(video.get("pubdate") or 0, timezone(timedelta(hours=8)))
            except (TypeError, ValueError, OverflowError, OSError):
                return False
            year, month = self.published
            if published.year != year or (month and published.month != month):
                return False
        return True


def _contains(text: str, name: str) -> bool:
    left = r"(?<![a-z0-9])" if name[0].isascii() and name[0].isalnum() else ""
    right = r"(?![a-z0-9])" if name[-1].isascii() and name[-1].isalnum() else ""
    return bool(re.search(left + re.escape(name) + right, text, re.I))


def plan_video_retrieval(question: str, query: str, scope: RetrievalScope | None) -> VideoPlan:
    rows = retrieval_video_catalog(scope)
    return match_videos(question, query, scope, rows)


def match_videos(question: str, query: str, scope: RetrievalScope | None, rows: list[dict]) -> VideoPlan:
    current = scope or RetrievalScope()
    signals = (question.casefold(), query.casefold())
    authors = {
        name for row in rows if (name := (row.get("author") or "").strip().casefold())
        and any(re.search(
            r"(?:作者|up\s*主|up|博主)\s*[:：]?\s*" + re.escape(name) +
            r"(?![a-z0-9])|(?<![a-z0-9])" + re.escape(name) +
            r"\s*(?:的|推荐|用的|怎么|给出|讲的|说的|视频里|视频中)", text, re.I
        ) for text in signals)
    }
    # 避免把短名称当成长昵称的子串。
    authors = {a for a in authors if not any(a != b and a in b for b in authors)}
    titles = {(row.get("title") or "").strip().casefold() for row in rows}
    titles.discard("")
    quoted = {name.strip().casefold() for name in re.findall(r"《([^》]+)》", question + " " + query)}
    titles = {title for title in titles if title in quoted or
              len(title) >= 6 and any(_contains(text, title) for text in signals)}
    titles = {t for t in titles if not any(t != other and t in other for other in titles)}
    date = re.search(r"(?<!\d)(20\d{2})年(?:\s*(1[0-2]|0?[1-9])月)?\s*(?:发布|上传|投稿)", question)
    if authors or titles or date:
        def published_in_period(row):
            if not date:
                return True
            published = row.get("published_at")
            if not isinstance(published, datetime):
                return False
            local = published.astimezone(timezone(timedelta(hours=8)))
            return local.year == int(date[1]) and (not date[2] or local.month == int(date[2]))

        matches = [row for row in rows if row["eligible"]
                   and (not authors or (row.get("author") or "").strip().casefold() in authors)
                   and (not titles or (row.get("title") or "").strip().casefold() in titles)
                   and published_in_period(row)]
        ids = [row["video_id"] for row in matches]
        label = "、".join(part for part in [
            "作者「" + "、".join(sorted({row['author'] for row in rows if (row.get('author') or '').strip().casefold() in authors})) + "」" if authors else "",
            "指定标题" if titles else "",
            f"发布时间「{date[0]}」" if date else "",
        ] if part)
        filters = {"authors": tuple(sorted(authors)), "titles": tuple(sorted(titles)),
                   "published": (int(date[1]), int(date[2]) if date[2] else None) if date else None}
        if not ids:
            return VideoPlan(scope, query, label=label, blocked=True, **filters)
        # 不把作者/标题当成必须出现在字幕里的关键词。
        inside = query
        for name in sorted(authors | titles, key=len, reverse=True):
            inside = re.sub(re.escape(name) + r"(?:\s*的)?", " ", inside, flags=re.I)
        if date:
            inside = re.sub(re.escape(date[0]) + r"(?:\s*的)?", " ", inside)
        inside = re.sub(r"(?:作者|UP\s*主|博主)\s*[:：]?", " ", inside, flags=re.I).strip(" 《》:：，,")
        return VideoPlan(current.model_copy(update={"video_ids": ids}), inside or query,
                         label=label, count=len(ids), **filters)

    # 弱标题/简介/区域匹配只增加一条候选来源，不缩窄用户选定的范围。
    terms = set(query_terms(query.casefold()))
    ranked = []
    for row in rows:
        if not row["eligible"]:
            continue
        title, area, desc = ((row.get(k) or "").casefold() for k in ("title", "stage_name", "description"))
        score = sum(3 if term in title else 2 if term in area else 1 if term in desc else 0 for term in terms)
        if score:
            ranked.append((score, row["video_id"]))
    hints = tuple(vid for _, vid in sorted(ranked, key=lambda pair: (-pair[0], pair[1]))[:8])
    return VideoPlan(scope, query, hints=hints)


def source_context(hit: dict) -> str:
    meta = hit["meta"]
    fields = [("视频标题", meta.get("title")), ("作者", meta.get("author")),
              ("发布时间", str(meta["published_at"])[:10] if meta.get("published_at") else None),
              ("关卡／区域", meta.get("stage_name"))]
    return " · ".join(f"{key}：{value}" for key, value in fields if value)
