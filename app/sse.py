"""SSE（Server-Sent Events）格式化与流式响应辅助。"""
import json
import time
from fastapi.responses import StreamingResponse


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_response(gen) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def poll_task_stream(task_id: str, get_snapshot) -> str:
    """轮询任务状态直到终态，逐次 yield SSE 文本。"""
    while True:
        snap = get_snapshot(task_id)
        yield format_sse(snap["event"], snap["data"])
        if snap["event"] == "done":
            break
        time.sleep(0.6)
