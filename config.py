"""全局配置：从 .env 读取密钥与参数，未配置时使用默认值。"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ===== LLM 生成（DeepSeek）=====
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ===== Embedding（硅基流动 bge-m3）=====
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

# ===== ASR（faster-whisper）=====
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")      # tiny/base/small/medium/large-v3
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "zh")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_BATCH_SIZE = int(os.getenv("WHISPER_BATCH_SIZE", "4"))
if WHISPER_BATCH_SIZE < 0:
    raise ValueError("WHISPER_BATCH_SIZE 必须为非负整数（0 表示逐段转写）")
BILI_AUDIO_MAX_MIB = max(1, int(os.getenv("BILI_AUDIO_MAX_MIB", "50")))

# ===== 文本切分 =====
CHUNK_TARGET_CHARS = int(os.getenv("CHUNK_TARGET_CHARS", "400"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "50"))

# ===== 检索 =====
TOP_K = int(os.getenv("TOP_K", "5"))

# ===== 存储目录 =====
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
CHROMA_DIR = DATA_DIR / "chroma"

CHROMA_DIR.mkdir(parents=True, exist_ok=True)

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "video_knowledge")

# ===== PostgreSQL + pgvector =====
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_USER = os.getenv("PG_USER", "rag")
PG_PASSWORD = os.getenv("PG_PASSWORD", "rag123456")
PG_DB = os.getenv("PG_DB", "video_rag")
# bge-m3 向量维度
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
# 余弦距离阈值：高于此值视为不相关，避免硬答（0~2，越小越相似）。
# 实测相关片段约 0.38~0.46，0.5+ 明显偏弱，故默认 0.5 以滤掉弱相关引用。
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "0.5"))

# ===== Rerank（硅基 bge-reranker 二次精排）=====
# 开关：开启后候选放宽到 RERANK_CANDIDATES，用 cross-encoder 重排，按分数过滤取 top_k。
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "1").lower() not in ("0", "false", "no")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
# 送入 rerank 的候选数（放宽召回，交给 rerank 精排）
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "15"))
# rerank 分数下限：低于此值视为无关引用剔除（实测噪声 <0.02、错字弱相关≈0.06、正常相关 >0.2）
RERANK_MIN_SCORE = float(os.getenv("RERANK_MIN_SCORE", "0.05"))
RERANK_TIMEOUT = int(os.getenv("RERANK_TIMEOUT", "15"))
# 相邻片段扩展：命中片段并入同视频前后各 N 个相邻片段，避免一个完整操作被
# chunk 边界切断后只召回半截。0 表示关闭。
NEIGHBOR_WINDOW = int(os.getenv("NEIGHBOR_WINDOW", "1"))

# ===== Agent 外部搜索 =====
# 本地命中虽能通过最低引用门槛，但最高 rerank 分低于该值时，认为证据不足，
# 不直接据此作答，改为建议搜索 B 站候选视频。设为 0 则只在完全无命中时搜索。
# 注：门槛过高会把"相关度刚好偏低但实际可答"的问题误判为不足，实测 0.20 会卡掉
# 最高分 0.19~0.20 的正常问题，故下调到 0.10（真正的弱相关/无关通常在 0.05 以下）。
EXTERNAL_SEARCH_RERANK_THRESHOLD = float(
    os.getenv("EXTERNAL_SEARCH_RERANK_THRESHOLD", "0.10")
)
EXTERNAL_SEARCH_LIMIT = int(os.getenv("EXTERNAL_SEARCH_LIMIT", "5"))
# 在本地检索候选通过相关度门槛后，再由 LLM 判断片段是否真正覆盖问题。
# 关闭时保持原有行为；核验调用失败时也会安全回退到原有回答路径。
ANSWERABILITY_CHECK_ENABLED = os.getenv("ANSWERABILITY_CHECK_ENABLED", "1").lower() not in (
    "0", "false", "no"
)
