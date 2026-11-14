"""问答路由：POST /api/ask，SSE 流式返回答案与引用。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictBool

from agents.game import GameState, stream_game_answer
from app import services, tasks
from app.sse import sse_response, format_sse

router = APIRouter(prefix="/api", tags=["qa"])


class AskBody(BaseModel):
    question: str
    top_k: int | None = None
    history: list | None = None
    game_state: GameState | None = None


class AudioConfirmationBody(BaseModel):
    approved: StrictBool
    selected_bvids: list[str] | None = None


@router.post("/ask/{task_id}/audio-confirmation")
def confirm_audio(task_id: str, body: AudioConfirmationBody):
    try:
        accepted = tasks.decide_audio_confirmation(task_id, body.approved, body.selected_bvids)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not accepted:
        raise HTTPException(409, "这次转写确认已结束或已提交")
    return {"accepted": True}


@router.post("/ask")
def ask(body: AskBody):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")

    def gen():
        task_id = tasks.create_task("ask", "")
        tasks.update_task(task_id, status="processing")
        try:
            yield format_sse("task", {"task_id": task_id})
            if body.game_state is None:
                events = services.stream_answer(question, body.top_k, body.history, task_id)
            else:
                events = stream_game_answer(
                    question, body.game_state, top_k=body.top_k, task_id=task_id, answer=services.stream_answer,
                )
            for item in events:
                yield format_sse(item["event"], item["data"])
        finally:
            tasks.finish_ephemeral(task_id)

    return sse_response(gen())
