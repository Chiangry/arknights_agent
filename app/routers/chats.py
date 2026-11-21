from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from app import chat_store
from index.catalog import RetrievalScope

router = APIRouter(prefix="/api/chat/threads", tags=["chat history"])
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=350)]


class CreateThread(BaseModel):
    id: UUID
    title: Title = chat_store.DEFAULT_TITLE
    scope: RetrievalScope = Field(default_factory=RetrievalScope)
    scoped_video_title: Title | None = None


class UpdateThread(BaseModel):
    title: Title | None = None
    scope: RetrievalScope | None = None
    scoped_video_title: Title | None = None
    agent_enabled: bool | None = None


@router.get("")
def list_threads():
    return chat_store.list_threads()


@router.post("", status_code=201)
def create_thread(body: CreateThread):
    return chat_store.create_thread(body.id, body.title, body.scope.model_dump(), body.scoped_video_title)


@router.get("/{thread_id}")
def get_thread(thread_id: UUID):
    thread = chat_store.get_thread(thread_id)
    if thread is None:
        raise HTTPException(404, "会话不存在")
    return thread


@router.patch("/{thread_id}")
def update_thread(thread_id: UUID, body: UpdateThread):
    changes = body.model_dump(exclude_unset=True)
    for field in ("title", "scope", "agent_enabled"):
        if field in changes and changes[field] is None:
            raise HTTPException(422, f"{field} 不能为空")
    thread = chat_store.update_thread(thread_id, changes)
    if thread is None:
        raise HTTPException(404, "会话不存在")
    return thread


@router.delete("/{thread_id}", status_code=204)
def delete_thread(thread_id: UUID):
    if not chat_store.delete_thread(thread_id):
        raise HTTPException(404, "会话不存在")
