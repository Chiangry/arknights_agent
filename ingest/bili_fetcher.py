"""B站视频输入源。

优先级：
  1. 直接调 B 站官方接口抓 CC/AI 字幕（view 拿 cid → player/wbi/v2 拿字幕地址）
     → 带时间戳文本，零转写、最准
  2. 无字幕时兜底：yt-dlp 下载音频 → faster-whisper 转写

说明：yt-dlp 当前对 B 站 AI 字幕（ai-zh）提取不稳定，常返回空，因此字幕
改为直接请求官方接口；yt-dlp 仅用于兜底音频下载。
"""
import html
import json
import logging
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import requests
from http.cookiejar import MozillaCookieJar
import yt_dlp
from yt_dlp.networking import Request

import config
from ingest.transcribe import transcribe

_audio_video_locks = tuple(Lock() for _ in range(16))
logger = logging.getLogger(__name__)


def is_bili_url(target: str) -> bool:
    """判断目标是 B 站链接（http 链接或 BV 号）。"""
    return bool(re.search(r"bilibili\.com", target, re.I)) or bool(
        re.search(r"^BV[0-9A-Za-z]{10}", target)
    )


def parse_bvid(target: str) -> str | None:
    m = re.search(r"(BV[0-9A-Za-z]{10})", target)
    return m.group(1) if m else None


def _plain_text(value: str) -> str:
    """清理搜索接口标题/简介中的 HTML 高亮标签。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Referer": "https://www.bilibili.com",
    })
    cookie_path = config.BASE_DIR / "cookies.txt"
    if cookie_path.exists():
        cj = MozillaCookieJar(cookie_path)
        cj.load(ignore_discard=True, ignore_expires=True)
        s.cookies = cj
    return s


def _view_info(s: requests.Session, bvid: str) -> dict:
    r = s.get("https://api.bilibili.com/x/web-interface/view",
              params={"bvid": bvid}, timeout=20)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"获取视频信息失败：{d.get('message')}")
    return d["data"]


def fetch_video_metadata(bvid: str) -> dict:
    """只读取平台档案，不下载视频或字幕。"""
    from datetime import datetime, timezone
    with _session() as session:
        info = _view_info(session, bvid)
    return {
        'title': info.get('title'), 'author': info.get('owner', {}).get('name'),
        'cover_url': info.get('pic'), 'description': info.get('desc'),
        'duration_seconds': info.get('duration'),
        'published_at': datetime.fromtimestamp(info['pubdate'], timezone.utc) if info.get('pubdate') else None,
    }


def search_bili_videos(keyword: str, limit: int = 5) -> list[dict]:
    """搜索 B 站视频，返回适合向用户展示的精简候选。

    该函数只读取公开搜索结果，不下载视频、字幕，也不会写入知识库。
    搜索接口偶有调整，因此同时尝试旧路径和当前 WBI 路径；调用方可安全地把
    ``RuntimeError`` 作为一次外部工具失败处理。
    """
    keyword = keyword.strip()
    if not keyword:
        return []
    limit = max(1, min(limit, 10))
    s = _session()
    params = {"keyword": keyword, "search_type": "video", "page": 1, "page_size": limit}
    last_message = ""
    payload = None
    for endpoint in (
        "https://api.bilibili.com/x/web-interface/search/type",
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
    ):
        try:
            response = s.get(endpoint, params=params, timeout=15)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            last_message = str(exc)
            continue
        if data.get("code") == 0:
            payload = data.get("data") or {}
            break
        last_message = data.get("message") or f"错误码 {data.get('code')}"
    if payload is None:
        raise RuntimeError(f"B站搜索失败：{last_message or '服务暂不可用'}")

    videos = []
    for item in payload.get("result") or []:
        bvid = item.get("bvid")
        if not bvid:
            continue
        duration = item.get("duration") or ""
        cover = item.get("pic") or ""
        if cover.startswith("//"):
            cover = "https:" + cover
        videos.append({
            "bvid": bvid,
            "title": _plain_text(item.get("title", "")) or bvid,
            "author": _plain_text(item.get("author", "")),
            "description": _plain_text(item.get("description", "")),
            "duration": duration,
            "play": int(item.get("play") or 0),
            "pubdate": int(item.get("pubdate") or 0),
            "cover": cover,
            "url": f"https://www.bilibili.com/video/{bvid}",
        })
    return videos


def _api_subtitle(s: requests.Session, bvid: str, cid: int):
    """调官方 player 接口拿字幕地址。返回 (url, label)，无则 (None, None)。"""
    endpoints = [
        "https://api.bilibili.com/x/player/wbi/v2",
        "https://api.bilibili.com/x/player/v2",
    ]
    for ep in endpoints:
        r = s.get(ep, params={"bvid": bvid, "cid": cid}, timeout=20)
        d = r.json()
        if d.get("code") != 0:
            continue
        lst = ((d.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        # 优先 UP 主 CC 字幕（lan 不含 ai），其次 AI 字幕
        lst = sorted(lst, key=lambda x: 1 if str(x.get("lan", "")).startswith("ai-") else 0)
        for it in lst:
            u = it.get("subtitle_url")
            if not u:
                continue
            if u.startswith("//"):
                u = "https:" + u
            label = "AI字幕" if str(it.get("lan", "")).startswith("ai-") else "CC字幕"
            return u, label
    return None, None


def fetch_subtitles(url: str):
    """抓取 B 站字幕，返回 (segments, source, title, author)。无字幕 (None, None, None, None)。

    segments: [(start_秒, end_秒, text), ...]
    """
    bvid = parse_bvid(url)
    if not bvid:
        return None, None, None, None
    s = _session()
    info = _view_info(s, bvid)
    title = info.get("title") or bvid
    author = (info.get("owner") or {}).get("name") or ""
    sub_url, label = _api_subtitle(s, bvid, info["cid"])
    if not sub_url:
        return None, None, title, author

    data = s.get(sub_url, timeout=30).json()
    body = data.get("body") if isinstance(data, dict) else None
    if not body:
        return None, None, title, author

    segments = []
    for item in body:
        text = (item.get("content") or "").strip()
        if text:
            segments.append((float(item["from"]), float(item["to"]), text))
    return segments, label, title, author


def probe_subtitle(url: str) -> dict:
    """检测当前环境对该视频能否直接获取字幕。
    返回 {cookie, has_subtitle, subtitle_type, duration}。不下载音频、不转写。"""
    cookie_exists = (config.BASE_DIR / "cookies.txt").exists()
    bvid = parse_bvid(url)
    if not bvid:
        return {
            "cookie": cookie_exists,
            "has_subtitle": False,
            "subtitle_type": None,
            "duration": 0,
        }
    s = _session()
    info = _view_info(s, bvid)
    duration = round(_info_duration(info), 1)
    _, label = _api_subtitle(s, bvid, info["cid"])
    return {
        "cookie": cookie_exists,
        "has_subtitle": bool(label),
        "subtitle_type": label,
        "duration": duration,
    }


def _ydl_opts(extra: dict | None = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    cookie_path = config.BASE_DIR / "cookies.txt"
    if cookie_path.exists():
        opts["cookiefile"] = str(cookie_path)
    if extra:
        opts.update(extra)
    return opts


class AudioTooLarge(RuntimeError):
    """音轨超出单次下载上限。"""


def download_audio(url: str, out_dir: Path, on_progress=None) -> str:
    """通过 yt-dlp 选独立音轨，流式下载时执行字节上限。"""
    max_bytes = config.BILI_AUDIO_MAX_MIB * 1024 * 1024
    limit_error = f"音轨超过 {config.BILI_AUDIO_MAX_MIB} MiB 上限，已跳过"
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", url):
        url = f"https://www.bilibili.com/video/{url}"
    opts = _ydl_opts({
        "format": "bestaudio[protocol^=http][protocol!*=dash][protocol!*=m3u8]",
        "socket_timeout": 20,
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get("vcodec") != "none" or info.get("protocol") not in {"http", "https"}:
            raise RuntimeError("未找到可直接下载的独立音轨")
        if (info.get("filesize") or 0) > max_bytes:
            raise AudioTooLarge(limit_error)
        headers = {**(info.get("http_headers") or {}), "Accept-Encoding": "identity"}
        path = out_dir / "audio"
        with ydl.urlopen(Request(info["url"], headers=headers)) as response:
            total = int(response.headers.get("Content-Length") or 0)
            if total > max_bytes:
                raise AudioTooLarge(limit_error)
            downloaded = 0
            with path.open("wb") as output:
                while block := response.read(min(64 * 1024, max_bytes - downloaded + 1)):
                    downloaded += len(block)
                    if downloaded > max_bytes:
                        raise AudioTooLarge(limit_error)
                    output.write(block)
                    if on_progress:
                        on_progress(downloaded, total)
            if not downloaded or (total and downloaded != total):
                raise RuntimeError("音频下载不完整")
        return str(path)


def _open_transcript_cache():
    return sqlite3.connect(config.DATA_DIR / "bili_transcripts.sqlite3")


def get_cached_bili_transcript(bvid: str) -> list:
    path = config.DATA_DIR / "bili_transcripts.sqlite3"
    if not path.is_file():
        return []
    try:
        with closing(_open_transcript_cache()) as conn:
            row = conn.execute(
                "SELECT segments FROM transcripts WHERE bvid = ?", (bvid,),
            ).fetchone()
        return json.loads(row[0]) if row else []
    except (sqlite3.Error, ValueError):
        logger.warning("读取 B 站转写缓存失败", exc_info=True)
        return []


def _save_bili_transcript(bvid: str, segments: list) -> None:
    with closing(_open_transcript_cache()) as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                bvid TEXT PRIMARY KEY, segments TEXT NOT NULL, saved_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO transcripts VALUES (?, ?, ?)",
            (bvid, json.dumps(segments, ensure_ascii=False), time.time_ns()),
        )
        conn.execute("""
            DELETE FROM transcripts WHERE bvid IN (
                SELECT bvid FROM transcripts ORDER BY saved_at DESC LIMIT -1 OFFSET 16
            )
        """)


def transcribe_bili_audio(url: str, audio_dir: Path | None = None, on_progress=None) -> list:
    """同一 BV 复用近期转写文本，并避免进程内并发重复识别。"""
    bvid = parse_bvid(url)
    if not bvid or audio_dir is not None:
        return _transcribe_bili_audio(url, audio_dir, on_progress)
    with _audio_video_locks[hash(bvid) % len(_audio_video_locks)]:
        cached = get_cached_bili_transcript(bvid)
        if cached:
            return cached
        segments = _transcribe_bili_audio(bvid, None, on_progress)
        if segments:
            try:
                _save_bili_transcript(bvid, segments)
            except sqlite3.Error:
                logger.warning("保存 B 站转写缓存失败", exc_info=True)
        return segments


def _transcribe_bili_audio(url: str, audio_dir: Path | None, on_progress) -> list:
    """独立临时目录隔离并发任务，下载或转写异常时也清理。"""
    audio_dir = audio_dir or (config.DATA_DIR / "tmp_audio")
    audio_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="bili-", dir=audio_dir) as temp:
        if on_progress:
            on_progress("download", 0, 0)
        audio = download_audio(
            url, Path(temp),
            on_progress=(lambda done, total: on_progress("download", done, total)) if on_progress else None,
        )
        if on_progress:
            on_progress("transcribe", 0, 0)
        return transcribe(
            audio,
            on_progress=(lambda done, total: on_progress("transcribe", done, total)) if on_progress else None,
        )


def _info_duration(info: dict) -> float:
    """从 view 接口结果里取时长（秒）。
    注意字段单位不统一：`duration` 是秒，`timelength` 是毫秒。"""
    if info.get("duration") is not None:
        return float(info.get("duration") or 0)
    return float(info.get("timelength") or 0) / 1000.0


def fetch_bili_segments(url: str, audio_dir: Path | None = None, on_progress=None):
    """统一入口：优先字幕，兜底音频转写。返回 (segments, source, title, author)。

    on_progress(stage, done, total)：下载按字节、转写按秒；未知总量为 0。
    """
    segments, source, title, author = fetch_subtitles(url)
    if segments:
        return segments, source, title, author

    print("  ⚠️ 未找到字幕，改用下载音频 + whisper 转写兜底 ...")
    segments = transcribe_bili_audio(url, audio_dir, on_progress)
    # 转写兜底时再补一次标题/作者
    if title is None:
        bvid = parse_bvid(url)
        if bvid:
            try:
                info = _view_info(_session(), bvid)
                title = info.get("title") or bvid
                author = (info.get("owner") or {}).get("name") or ""
            except Exception:
                title, author = bvid, ""
        else:
            title, author = url, ""
    return segments, "音频转写", title, author
