"""问答路由：POST /api/ask，SSE 流式返回答案与引用。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictBool
from functools import partial
from uuid import UUID
from index.catalog import RetrievalScope

from agents.game import GameState, stream_game_answer
from app import chat_store, chat_turns, services, tasks
from app.sse import sse_response, format_sse
from rag.search_intent import search_intent

router = APIRouter(prefix="/api", tags=["qa"])


class AskBody(BaseModel):
    question: str
    top_k: int | None = None
    history: list | None = None
    game_state: GameState | None = None
    scope: RetrievalScope | None = None
    thread_id: UUID | None = None
    request_id: UUID | None = None
    web_search: StrictBool = False


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

    history, game_state, scope = body.history, body.game_state, body.scope
    turn = None
    if body.thread_id is not None:
        if body.request_id is None:
            raise HTTPException(422, "保存会话消息需要 request_id")
        try:
            turn = chat_store.begin_turn(body.thread_id, body.request_id, question)
        except chat_store.ChatConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        if turn is None:
            raise HTTPException(404, "会话不存在")
        if "replay" in turn:
            return sse_response(chat_turns.replay(turn["replay"]))
        thread = turn["thread"]
        history = turn["history"]
        game_state = GameState.model_validate(thread["game_state"] or {}) if thread["agent_enabled"] else None
        scope = RetrievalScope.model_validate(thread["scope"])

    def generate():
        task_id = tasks.create_task("ask", "")
        tasks.update_task(task_id, status="processing")
        try:
            yield {"event": "task", "data": {"task_id": task_id}}
            options = {}
            if scope and scope.restricted:
                options["scope"] = scope
            if body.web_search:
                options["web_search"] = True
            answer = partial(services.stream_answer, **options) if options else services.stream_answer
            route = search_intent(question, body.web_search)
            if game_state is None or not route.local:
                events = answer(question, body.top_k, history, task_id)
            else:
                events = stream_game_answer(
                    question, game_state, top_k=body.top_k, task_id=task_id, answer=answer,
                    **({"web_requested": True} if route.source else {}),
                )
            yield from events
        finally:
            tasks.finish_ephemeral(task_id)

    if turn:
        return sse_response(chat_turns.start(body.thread_id, turn["assistant_id"], generate))
    return sse_response(format_sse(item["event"], item["data"]) for item in generate())
