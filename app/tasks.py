"""内存任务注册表：导入长任务的状态与进度（原型阶段用内存，重启即清空）。"""
import threading
import uuid
import time

_lock = threading.Condition()
_tasks: dict[str, dict] = {}

# 解析步骤（与前端四步对应）
STEPS = ["fetch", "chunk", "embed", "index"]
STEP_LABELS = {
    "fetch": "获取字幕 / 语音转写",
    "chunk": "切分文本片段",
    "embed": "向量化 embedding",
    "index": "写入向量索引",
}


def create_task(kind: str, ref: str) -> str:
    return reserve_task(kind, ref, reuse=False)[0]


def reserve_task(kind: str, ref: str, *, reuse: bool = True) -> tuple[str, bool]:
    task_id = uuid.uuid4().hex[:12]
    with _lock:
        if reuse:
            for existing, task in _tasks.items():
                if task["kind"] == kind and task["ref"] == ref and task["status"] in ("queued", "processing"):
                    return existing, False
        _tasks[task_id] = {
            "task_id": task_id,
            "kind": kind,            # bili / local
            "ref": ref,
            "status": "queued",     # queued/processing/done/error
            "step": "fetch",
            "step_index": 0,
            "pct": 0,
            "message": "排队中",
            "video_id": None,
            "source": None,
            "chunk_count": 0,
            "error": None,
            "created_at": time.time(),
            "pause_requested": False,
            "paused": False,
        }
    return task_id, True


def get_task(task_id: str) -> dict | None:
    with _lock:
        t = _tasks.get(task_id)
        return dict(t) if t else None


def update_task(task_id: str, **fields) -> None:
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].update(fields)
            _lock.notify_all()


def set_paused(task_id: str, paused: bool) -> bool:
    with _lock:
        task = _tasks.get(task_id)
        if not task or task["status"] not in ("queued", "processing"):
            return False
        task["pause_requested"] = paused
        _lock.notify_all()
        return True


def finish_ephemeral(task_id: str) -> None:
    with _lock:
        task = _tasks.pop(task_id, None)
        if task:
            task["status"] = "done"
        _lock.notify_all()


def request_audio_confirmation(task_id: str, timeout: float, candidates: list[str]) -> bool:
    with _lock:
        task = _tasks.get(task_id)
        if (not task or task["kind"] != "ask" or task["status"] != "processing"
                or "audio_confirmation_deadline" in task):
            return False
        task["audio_confirmation_deadline"] = time.monotonic() + timeout
        task["audio_candidates"] = tuple(candidates)
        return True


def decide_audio_confirmation(task_id: str, approved: bool, selected_bvids: list[str] | None = None) -> bool:
    with _lock:
        task = _tasks.get(task_id)
        if (not task or task["kind"] != "ask" or task["status"] != "processing"
                or "audio_selection" in task
                or time.monotonic() >= task.get("audio_confirmation_deadline", 0)):
            return False
        candidates = task["audio_candidates"]
        if selected_bvids is not None and (
            approved != bool(selected_bvids) or not set(selected_bvids).issubset(candidates)
        ):
            raise ValueError("只能选择本轮确认卡片中的视频")
        selected = set(selected_bvids if selected_bvids is not None else candidates)
        task["audio_selection"] = tuple(bvid for bvid in candidates if approved and bvid in selected)
        _lock.notify_all()
        return True


def poll_audio_confirmation(task_id: str) -> tuple[str, tuple[str, ...]]:
    """每次最多等一秒，使 SSE 能保活并及时感知断开。"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return "expired", ()
        deadline = task["audio_confirmation_deadline"]
        _lock.wait_for(
            lambda: "audio_selection" in task or task["status"] != "processing",
            timeout=max(0, min(1, deadline - time.monotonic())),
        )
        if task["status"] != "processing":
            return "expired", ()
        if "audio_selection" in task:
            selected = task["audio_selection"]
            return ("approved" if selected else "declined"), selected
        return ("expired" if time.monotonic() >= deadline else "pending"), ()


def wait_if_paused(task_id: str, cancelled=None) -> float:
    """在处理边界暂停，返回暂停耗时供进度估算扣除。"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return 0.0
        start = time.monotonic()
        while task["pause_requested"] and task["status"] in ("queued", "processing"):
            if cancelled is not None and cancelled.is_set():
                break
            task["paused"] = True
            _lock.wait(timeout=0.5 if cancelled is not None else None)
        was_paused = task["paused"]
        task["paused"] = False
        return time.monotonic() - start if was_paused else 0.0


def snapshot(task_id: str) -> dict:
    """生成 SSE 推送用的纯数据快照。"""
    t = get_task(task_id)
    if not t:
        return {"event": "error", "data": {"message": "任务不存在"}}
    done = t["status"] in ("done", "error")
    payload = {
        "task_id": t["task_id"],
        "status": t["status"],
        "step": t["step"],
        "step_index": t["step_index"],
        "step_label": STEP_LABELS.get(t["step"], t["step"]),
        "pct": t["pct"],
        "message": t["message"],
        "video_id": t["video_id"],
        "source": t["source"],
        "chunk_count": t["chunk_count"],
        "error": t["error"],
        "pause_requested": t["pause_requested"],
        "paused": t["paused"],
    }
    return {"event": "done" if done else "progress", "data": payload}
