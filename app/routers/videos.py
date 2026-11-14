"""视频路由：创建导入任务、视频列表、任务进度 SSE。"""
import uuid
import hashlib
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, UploadFile, File, HTTPException
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import config
from app import tasks, services
from app.sse import sse_response, poll_task_stream
from ingest.bili_fetcher import get_cached_bili_transcript, is_bili_url, parse_bvid, search_bili_videos
from index.store import video_exists

router = APIRouter(prefix="/api", tags=["videos"])

UPLOAD_DIR = config.DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4a", ".mp3", ".wav", ".flac", ".webm"}


class PauseBody(BaseModel):
    paused: bool


class CachedImportBody(BaseModel):
    bvid: str = Field(pattern=r"^BV[0-9A-Za-z]{10}$")
    title: str = Field(max_length=300)
    author: str = Field(default="", max_length=200)


@router.post("/videos/import-transcript")
def import_transcript(background: BackgroundTasks, body: CachedImportBody):
    if video_exists(body.bvid):
        return {"status": "exists"}
    segments = get_cached_bili_transcript(body.bvid)
    if not segments:
        raise HTTPException(409, "转写缓存已失效，请在视频库重新导入")
    task_id, created = tasks.reserve_task("bili", body.bvid)
    if created:
        background.add_task(services.run_cached_ingest, task_id, body.bvid, segments, body.title, body.author)
    return {"status": "queued", "task_id": task_id}


async def reserve_import(kind: str, video_id: str) -> tuple[str, bool]:
    if await run_in_threadpool(video_exists, video_id):
        raise HTTPException(409, "这个视频已在知识库中，已跳过重复导入")
    return tasks.reserve_task(kind, video_id)


@router.post("/videos")
async def create_import(
    background: BackgroundTasks,
    kind: str = Form("bili"),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    """创建解析任务。kind=bili 时传 url；kind=local 时传 file。返回 task_id。"""
    if kind == "bili":
        if not url or not url.strip():
            raise HTTPException(400, "缺少 B 站链接")
        video_id = parse_bvid(url.strip())
        if not video_id:
            raise HTTPException(400, "不是有效的 B 站链接 / BV 号")
        task_id, created = await reserve_import("bili", video_id)
        if created:
            background.add_task(services.run_ingest, task_id, "bili", video_id)
        return {"task_id": task_id, "kind": "bili"}

    elif kind == "local":
        if file is None:
            raise HTTPException(400, "缺少上传文件")
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"不支持的文件类型 {ext}")
        digest = await run_in_threadpool(hashlib.file_digest, file.file, "sha256")
        video_id = f"local:{digest.hexdigest()}"
        task_id, created = await reserve_import("local", video_id)
        if created:
            saved = UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}{ext}"
            try:
                await file.seek(0)
                with saved.open("wb") as output:
                    while block := await file.read(1024 * 1024):
                        output.write(block)
            except BaseException:
                saved.unlink(missing_ok=True)
                tasks.update_task(task_id, status="error", error="上传未完成")
                raise
            background.add_task(
                services.run_ingest, task_id, "local", video_id,
                file_path=str(saved), title=file.filename,
            )
        return {"task_id": task_id, "kind": "local", "title": file.filename}

    raise HTTPException(400, "kind 只能是 bili 或 local")


@router.get("/videos")
def list_videos():
    return {"videos": services.get_videos()}


@router.get("/subtitle-check")
def subtitle_check(url: str):
    """检测当前能否直接获取该视频字幕，供前端在导入前提示。"""
    url = (url or "").strip()
    if not url:
        raise HTTPException(400, "缺少 B 站链接")
    if not is_bili_url(url):
        raise HTTPException(400, "不是有效的 B 站链接 / BV 号")
    try:
        return services.check_subtitle(url)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"检测失败：{e}") from e


@router.get("/search/bilibili")
def search_bilibili(query: str, limit: int = 5):
    """只搜索 B 站候选视频，不下载、不转写、不入库。"""
    query = (query or "").strip()
    if not query:
        raise HTTPException(400, "搜索关键词不能为空")
    try:
        return {"query": query, "videos": search_bili_videos(query, limit)}
    except Exception as e:  # noqa: BLE001 - 统一为 API 可读错误
        raise HTTPException(502, f"B站搜索失败：{e}") from e


@router.get("/tasks/{task_id}/stream")
def task_stream(task_id: str):
    if tasks.get_task(task_id) is None:
        raise HTTPException(404, "任务不存在")
    return sse_response(poll_task_stream(task_id, tasks.snapshot))


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: str, body: PauseBody):
    if not tasks.set_paused(task_id, body.paused):
        raise HTTPException(409, "任务已结束或不存在")
    return tasks.snapshot(task_id)["data"]
