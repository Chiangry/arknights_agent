# 视频 RAG 知识库

读取本地视频，转成文本后向量化入库，实现基于内容的问答（回答带视频时间戳定位）。

## 技术栈
| 环节 | 方案 |
|---|---|
| 语音转文字 | faster-whisper（本地，small 模型） |
| 向量化 | 硅基流动 bge-m3（云端 API，1024 维） |
| 向量存储 | PostgreSQL + pgvector（Docker，HNSW 余弦索引） |
| 回答生成 | DeepSeek（deepseek-chat） |

## 数据库（Docker pgvector）
向量与视频元数据都在 PostgreSQL 里，用官方 pgvector 镜像一键启动，宿主端口映射到 **5433**（避开本机已占用的 5432）。

```bash
# 首次启动（init.sql 自动建扩展、videos/chunks 表与 HNSW 索引）
docker run -d --name video-rag-pg --restart unless-stopped \
  -p 5433:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag123456 -e POSTGRES_DB=video_rag \
  -v pgdata:/var/lib/postgresql/data \
  -v "$PWD/deploy/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
  pgvector/pgvector:pg17

# 从旧 Chroma 文件库迁移已有向量（可选，省去重新转写）
python scripts/migrate_chroma.py
```
> 国内拉镜像慢可用加速器前缀：`docker.m.daocloud.io/pgvector/pgvector:pg17`。

## 环境
```bash
conda activate video_rag      # 已建好的 Python 3.11 环境
pip install -r requirements.txt
```

## 配置
编辑项目根目录 `.env`：
```
DEEPSEEK_API_KEY=sk-...        # DeepSeek（生成回答）
SILICONFLOW_API_KEY=sk-...     # 硅基流动（embedding）
# PostgreSQL + pgvector
PG_HOST=127.0.0.1
PG_PORT=5433
PG_USER=rag
PG_PASSWORD=rag123456
PG_DB=video_rag
SCORE_THRESHOLD=0.6            # 余弦距离阈值，超过视为不相关，避免硬答
```
> `.env` 已被 .gitignore 忽略，不会提交。

## 用法
在项目根目录运行：
```bash
# 1. 解析视频入库（本地文件 或 B站链接/BV号 均可）
python cli.py ingest 视频文件.mp4
python cli.py ingest "https://www.bilibili.com/video/BVxxxx"   # 或直接写 BV号

# 2. 基于知识库提问
python cli.py ask "你的问题"
```

## HTTP / SSE 接口（前端联调）
在 CLI 之外，`app/` 提供了一层 FastAPI 接口，供 Vite 前端调用。

启动（项目根目录，video_rag 环境）：
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# 交互式文档：http://127.0.0.1:8000/docs
```

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/videos` | 已入库视频列表（聚合 chunk 数、时长、来源） |
| GET | `/api/search/bilibili?query=关键词&limit=5` | 搜索 B 站候选视频；不下载、不入库 |
| POST | `/api/videos` | 创建解析任务，form 表单：`kind=bili&url=链接`，或 `kind=local&file=视频文件` → 返回 `{task_id}` |
| GET | `/api/tasks/{task_id}/stream` | SSE 推送解析进度，终态 `event: done/error` |
| POST | `/api/ask` | 问答，JSON `{question}`，SSE 流式返回 |

**进度 SSE**（`/api/tasks/{id}/stream`）逐帧推送：
```
event: progress
data: {"status":"processing","step":"fetch","step_index":0,"pct":45,"message":"取得 N 个文本片段（CC字幕）",...}
```
`step` 四步：`fetch`(获取字幕/转写) → `chunk`(切分) → `embed`(向量化) → `index`(写入索引)；终态 `status=done/error`。

**问答 SSE**（`/api/ask`）通过 `agent_step` 实时显示知识库检索、片段核验、生成草稿和答案复核。片段覆盖不足，或本地草稿未能回答核心问题时，会根据缺失信息搜索 B 站。答案通过复核后，接口发送 `citations`、正文 `delta` 和 `done`。

外部搜索通过 `external_search` 返回候选卡片，按排名从前五个候选中取最多三份可用字幕。字幕不足以回答时，聊天页会询问是否下载并转写。确认后才会依次尝试排名前两个候选的独立音轨，并显示下载和转写进度。跳过或两分钟内未确认时，保留候选卡片。字幕与转写均在当前请求内临时检索，可与本地片段一起生成带时间戳的答案。

**对局 Agent** 位于 `agents/game/`。向 `/api/ask` 传入 `game_state`（首轮可传 `{}`）启用，后续请求带上最新 `game_state` 事件返回的状态。Agent 负责合并对局信息、排除不可执行动作和决定是否追问；需要查证时，它把检索词和对局约束交给 `app/services.py` 的共享问答流程。知识库检索、B 站补查、转写确认和引用不另写一套。

## 前端（Vite + Vue3 + TS + Pinia）
代码在 `frontend/`。技术栈：Vue3 Composition API + TypeScript + Vue Router(hash) + Pinia + SCSS，请求走 fetch，进度用 EventSource、问答用 fetch 解析 SSE。

```bash
# 1. 先起后端（项目根目录）
uvicorn app.main:app --port 8000 --reload

# 2. 另开终端起前端（frontend/ 目录，Node 18+）
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173
```

前端目录：
```
frontend/src/
├── api/        # client(封装) / videos(列表·导入·进度SSE) / qa(问答流)
├── stores/     # videos / parse(任务状态机) / chat(消息流)
├── views/      # LibraryView(添加视频) / ChatView(问答)
├── components/ # Sidebar / ImportPanel / ParseProgress / VideoList / ChatMessage / Composer / CitationTag
├── router/  types/  styles/
```
后端地址由 `frontend/.env.development` 的 `VITE_API_BASE` 控制。

## 验证示例
```
$ python cli.py ask "视频里他们准备小惊喜之前打算先做什么？"
🧠 回答:
他们在准备小惊喜之前打算先去吃饭。... [131s-168s]
```

## 混合检索（向量 + 全文）
- **背景**：纯向量（bge-m3 稠密向量）擅长语义近似，但精确定位具体术语会 miss（如"标准引擎"这种跨视频词，正确答案被挤到 top11）。
- **实现**：`index/tokenizer.py`（jieba 中文分词）→ chunks 表 `tokens` 列 + GIN 全文索引 → `store.hybrid_search`
  （向量 top50 + 全文 `to_tsquery` AND 精确召回 top50，RRF k=60 融合）；`rag/retriever.py` 走混合路径。
- **阈值豁免**：全文精确命中的 chunk（`lexical=True`）豁免 `SCORE_THRESHOLD`——关键词命中是强相关信号，
  即使向量距离偏大也保留，避免纯向量时代"正确答案超阈值被滤掉"。
- **评测**：`scripts/eval/eval_rag.py` 三视角。混合检索 HitRate@5 93.55% → **96.77%**，MRR 0.863 → **0.895**，
  救回"标准引擎有什么用？""卫戍协议"等纯向量 miss。
- 离线 BM25 概念验证见 `scripts/eval/eval_hybrid.py`。

## 说明与已知点
- 转写用 whisper small，口语/专有名词可能有少量错别字，但语义可理解，不影响检索与回答。
- 首次 ingest 会自动下载 whisper 模型（国内走 hf-mirror 镜像）。
- 每个视频以文件名（或 BV 号）作为 video_id，可叠加多个视频。

## B 站输入说明
- **字幕优先**：直接调 B 站官方接口获取字幕——`web-interface/view` 拿 `cid`，再用
  `player/wbi/v2` 拿字幕地址（优先 UP 主 CC 字幕，其次 AI 字幕 `ai-zh`），下载字幕 JSON
  解析为带时间戳文本。零转写、最准、秒级完成。
- **为何不用 yt-dlp 取字幕**：yt-dlp 对 B 站 AI 字幕提取不稳定，常返回空轨道；
  因此字幕改为官方接口，yt-dlp 仅用于无字幕时的音频下载兜底。
- **无字幕兜底**：官方接口也没有字幕时，下载独立音轨并用 Whisper 转写。导入与聊天共用每个音轨 `BILI_AUDIO_MAX_MIB`（默认 50 MiB）的下载上限。每次任务使用独立临时目录，完成或失败后清理，聊天转写文本仅用于当次问答。
- **批量转写**：本地文件、B 站导入和聊天补查共用 `WHISPER_BATCH_SIZE`，默认 `4`。在 `.env` 里设为 `8` 可试更大的批次，会增加内存占用；设为 `0` 恢复逐段转写。修改后重启后端。批量模式按批产出片段，因此进度更新和暂停可能要等当前批次结束。
- **登录态 cookie**：AI 字幕通常需要登录态。用浏览器扩展导出 Netscape 格式的 B 站 cookie，
  存为项目根目录 `cookies.txt`，`ingest/bili_fetcher.py` 会自动加载（已在 `.gitignore` 忽略）。
- **导入前检测**：`GET /api/subtitle-check?url=` 返回 `{cookie, has_subtitle, subtitle_type}`，
  前端「检测能否获取字幕」按钮据此提示，不下载音频、不转写。

## 多轮对话（会话历史）
- **传输**：`POST /api/ask` body 增加 `history: [{role, content}, ...]`，前端把最近 5 轮 Q/A 一并发送。
- **query 改写**：有历史时，后端先用 DeepSeek 把「历史 + 当前问题」重写为一个自包含、消解指代的检索
  query（如「它的第二种物品」→「自然物的用法」），再用它做 pgvector 召回，解决指代召回不准。
  改写失败自动回退用原问题；无历史时不做额外调用。
- **生成上下文**：历史消息与检索片段、当前问题一起拼入 DeepSeek messages，回答能结合前文。
- **前端**：聊天记录存 Pinia，自动传最近 5 轮；「新建会话」清空；会话用 `localStorage` 持久化，刷新不丢。

## 后续可扩展
- 视频删除接口与前端入口（`store.delete_video` 已就绪，外键 CASCADE 清理片段）
- 点击时间戳跳转到视频对应时间段、多视频筛选提问
- 切分参数调优、更大/更准的 whisper 模型
