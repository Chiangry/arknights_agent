"""FastAPI 入口：视频 RAG 知识库 HTTP/SSE 接口。

启动（项目根目录，video_rag 环境）：
    uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg import OperationalError
from psycopg.errors import UndefinedTable
from starlette.concurrency import run_in_threadpool

from app import chat_store
from app.routers import videos, qa, chats


@asynccontextmanager
async def lifespan(_app):
    try:
        await run_in_threadpool(chat_store.interrupt_running)
    except (UndefinedTable, OperationalError):
        logging.getLogger("uvicorn.error").warning("无法恢复聊天任务，请检查数据库及 005 聊天历史迁移")
    yield


app = FastAPI(title="视频 RAG 知识库", version="0.1.0", lifespan=lifespan)

# 聊天历史是私有数据，不向任意网站放开跨域访问。
default_origins = ",".join(f"http://{host}:{port}"
                           for host in ("localhost", "127.0.0.1") for port in (3000, 4173, 5173))
app.add_middleware(
    CORSMiddleware,
    allow_origins=[value.strip() for value in os.getenv("FRONTEND_ORIGINS", default_origins).split(",") if value.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(qa.router)
app.include_router(chats.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
