"""FastAPI 入口：视频 RAG 知识库 HTTP/SSE 接口。

启动（项目根目录，video_rag 环境）：
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import videos, qa

app = FastAPI(title="视频 RAG 知识库", version="0.1.0")

# 本地 Vite 开发端口与前端联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地原型，宽松放开；上线收敛为白名单
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(qa.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
