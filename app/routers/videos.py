"""视频路由：创建导入任务、视频列表、任务进度 SSE。"""
import uuid
import hashlib
import math
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, UploadFile, File, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StrictBool

import config
from app import tasks, services
from app.sse import sse_response, poll_task_stream
from ingest.bili_fetcher import get_cached_bili_transcript, is_bili_url, parse_bvid, search_bili_videos
from index.store import video_exists, delete_video, VideoImportBusy
from index.store import save_video_metadata, get_video, enrich_video_metadata, list_videos as stored_videos
from index.store import list_video_chunks, list_visual_windows
from index.catalog import CATALOG, RetrievalScope, VideoMetadata, suggest_video_category
from ingest.bili_fetcher import fetch_video_metadata
from ingest.visual_ingest import VisualRange

router = APIRouter(prefix="/api", tags=["videos"])

UPLOAD_DIR = config.DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4a", ".mp3", ".wav", ".flac", ".webm"}


class PauseBody(BaseModel):
    paused: bool


class VisualConfirmationBody(BaseModel):
    approved: StrictBool


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


async def reserve_with_metadata(kind: str, video_id: str, values: dict, *, selected: VisualRange | None = None):
    if selected:
        task_id, created = tasks.reserve_task("bili-visual", f"{video_id}:{selected.start}:{selected.seconds}")
    elif kind == "bili":
        task_id, created = tasks.reserve_task("bili-auto", video_id)
    else:
        task_id, created = await reserve_import(kind, video_id)
    if created:
        try:
            already_indexed = kind == "bili" and await run_in_threadpool(video_exists, video_id)
            if not already_indexed:
                await run_in_threadpool(save_video_metadata, video_id, values, create=True)
        except Exception:
            tasks.update_task(task_id, status="error", error="视频档案保存失败")
            raise
    return task_id, created


@router.post("/videos")
async def create_import(
    background: BackgroundTasks,
    request: Request,
    kind: str = Form("bili"),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    metadata: str = Form("{}"),
    visual_start: float | None = Form(None),
    visual_seconds: float | None = Form(None),
    approve_qwen: bool = Form(False),
):
    """创建解析任务。kind=bili 时传 url；kind=local 时传 file。返回 task_id。"""
    try:
        values = VideoMetadata.model_validate_json(metadata).model_dump(exclude_unset=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    selected = None
    if approve_qwen or visual_start is not None or visual_seconds is not None:
        if kind != "bili" or not approve_qwen or visual_start is None or visual_seconds is None:
            raise HTTPException(422, "画面解析需要 B 站视频、选定时间范围和 Qwen 上传授权")
        if not math.isfinite(visual_start) or not 0 <= visual_start <= 28800 or not 5 <= visual_seconds <= 55:
            raise HTTPException(422, "片段起点须在 0–28800 秒，时长须在 5–55 秒")
        _validate_mutation_origin(request)
        selected = VisualRange(visual_start, visual_seconds)
    if kind == "bili":
        if not url or not url.strip():
            raise HTTPException(400, "缺少 B 站链接")
        video_id = parse_bvid(url.strip())
        if not video_id:
            raise HTTPException(400, "不是有效的 B 站链接 / BV 号")
        task_id, created = await reserve_with_metadata("bili", video_id, values, selected=selected)
        if created:
            background.add_task(services.run_visual_ingest, task_id, video_id, selected)
        return {"task_id": task_id, "kind": "bili"}

    elif kind == "local":
        if file is None:
            raise HTTPException(400, "缺少上传文件")
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"不支持的文件类型 {ext}")
        digest = await run_in_threadpool(hashlib.file_digest, file.file, "sha256")
        video_id = f"local:{digest.hexdigest()}"
        task_id, created = await reserve_with_metadata("local", video_id, values)
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
def list_videos(game_id: str | None = None, category_id: str | None = None,
                query: str = "", limit: int | None = Query(None, ge=1, le=500), offset: int = Query(0, ge=0)):
    try:
        scope = RetrievalScope(game_id=game_id, category_id=category_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"videos": stored_videos(scope, query, limit, offset)}


@router.get("/catalog")
def catalog():
    return {"games": CATALOG}


@router.get("/video-metadata")
def preview_metadata(url: str):
    bvid = parse_bvid(url)
    if not bvid:
        raise HTTPException(422, "请输入 B 站链接或 BV 号")
    try:
        metadata = fetch_video_metadata(bvid)
        suggestion = suggest_video_category(metadata.get("title"), metadata.get("description"))
        return {**metadata, "bvid": bvid, "suggestion": suggestion}
    except Exception as exc:
        raise HTTPException(502, f"读取视频信息失败：{exc}") from exc


@router.post("/videos/{video_id}/refresh-metadata")
def refresh_metadata(video_id: str):
    video = get_video(video_id)
    if video is None:
        raise HTTPException(404, "视频不存在")
    if video.get('source_platform') != 'bilibili':
        raise HTTPException(422, "本地文件无法从 B 站补全信息")
    try:
        enrich_video_metadata(video_id, fetch_video_metadata(video_id))
    except Exception as exc:
        raise HTTPException(502, f"补全信息失败：{exc}") from exc
    return get_video(video_id)


@router.get("/videos/{video_id}")
def video_detail(video_id: str):
    video = get_video(video_id)
    if video is None:
        raise HTTPException(404, "视频不存在")
    return video


@router.get("/videos/{video_id}/visual-coverage")
def visual_coverage(video_id: str):
    video = get_video(video_id)
    if video is None:
        raise HTTPException(404, "视频不存在")
    return {"duration": video.get("duration_seconds"), "windows": list_visual_windows(video_id)}


@router.get("/videos/{video_id}/chunks")
def video_chunks(video_id: str, query: str = Query("", max_length=200),
                 limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    result = list_video_chunks(video_id, query.strip(), limit, offset)
    if result is None:
        raise HTTPException(404, "视频不存在")
    return result


@router.patch("/videos/{video_id}")
def edit_video(video_id: str, body: dict):
    try:
        save_video_metadata(video_id, body)
    except KeyError:
        raise HTTPException(404, "视频不存在")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return get_video(video_id)


@router.delete("/videos/{video_id}", status_code=204)
def remove_video(video_id: str, request: Request) -> Response:
    # 原型的 CORS 留作联调；删除不允许任意网页对本机知识库发起。
    _validate_mutation_origin(request)
    if tasks.video_import_pending(video_id):
        raise HTTPException(409, "该视频正在导入或补充证据，请等任务结束后再删除")
    try:
        removed = delete_video(video_id)
    except VideoImportBusy:
        raise HTTPException(409, "该视频正在处理，请稍后再删除") from None
    if not removed:
        raise HTTPException(404, "该视频未入库，或已被删除")
    return Response(status_code=204)


def _validate_mutation_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    same_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin is not None and origin != same_origin and origin not in config.VIDEO_DELETE_ORIGINS:
        raise HTTPException(403, "此页面不能执行该操作")


@router.post("/tasks/{task_id}/visual-confirmation", status_code=204)
def confirm_visual(task_id: str, body: VisualConfirmationBody, request: Request) -> Response:
    _validate_mutation_origin(request)
    if not tasks.decide_visual_confirmation(task_id, body.approved):
        raise HTTPException(409, "这次画面解析确认已结束或已提交")
    return Response(status_code=204)


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
