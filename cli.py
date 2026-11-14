"""视频 RAG 知识库命令行入口。

用法（在项目根目录运行）：
    python cli.py ingest <本地视频文件路径 或 B站链接/BV号>
    python cli.py ask   <问题>
"""
import os
import sys
import argparse
from pathlib import Path

from ingest.transcribe import transcribe
from ingest.chunker import build_chunks
from ingest.bili_fetcher import is_bili_url, parse_bvid, fetch_bili_segments
from index.embedder import embed_texts
from index.store import add_chunks
from rag.qa import ask


def _store_segments(video_id: str, segments: list) -> int:
    """切分 → 向量化 → 入库，返回 chunk 数量。"""
    print(f"      共转出 {len(segments)} 个文本片段")
    print("[切分 chunk] ...")
    chunks = build_chunks(segments)
    print(f"      共 {len(chunks)} 个 chunk")

    print("[向量化 embedding] ...")
    embeddings = embed_texts([c["text"] for c in chunks])

    print("[写入 Chroma] ...")
    add_chunks(video_id, chunks, embeddings)
    return len(chunks)


def cmd_ingest_local(video_path: str) -> None:
    if not os.path.exists(video_path):
        print(f"❌ 文件不存在: {video_path}")
        sys.exit(1)

    video_path = str(Path(video_path).resolve())
    video_id = Path(video_path).stem  # 文件名（不含后缀）作为 video id

    print(f"[1/3] 语音转文字: {video_path}")
    segments = transcribe(video_path)

    n = _store_segments(video_id, segments)
    print(f"✅ 入库完成: {video_id}，共 {n} 个 chunk")


def cmd_ingest_bili(url: str) -> None:
    print(f"解析 B 站视频: {url}")
    segments, source, _, _ = fetch_bili_segments(url)
    if not segments:
        print("❌ 未能取得任何字幕/转写文本，请检查链接或该视频是否可访问。")
        sys.exit(1)

    bvid = parse_bvid(url) or "bili_video"
    print(f"  文本来源: {source}")

    n = _store_segments(bvid, segments)
    print(f"✅ 入库完成: {bvid}（{source}），共 {n} 个 chunk")


def cmd_ingest(target: str) -> None:
    if is_bili_url(target):
        cmd_ingest_bili(target)
    else:
        cmd_ingest_local(target)


def cmd_ask(question: str) -> None:
    answer, hits = ask(question)
    print(f"\n🧠 回答:\n{answer}\n")
    print("参考片段（可据此校验）：")
    for h in hits:
        m = h["meta"]
        print(f"  · [{m['start']:.0f}s-{m['end']:.0f}s] {h['text'][:50]}...")


def main() -> None:
    parser = argparse.ArgumentParser(description="视频 RAG 知识库")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("ingest", help="解析视频入库（本地文件或B站链接）")
    p1.add_argument("target", help="本地视频文件路径，或 B站链接/BV号")

    p2 = sub.add_parser("ask", help="基于知识库提问")
    p2.add_argument("question", help="问题内容")

    args = parser.parse_args()

    if args.cmd == "ingest":
        cmd_ingest(args.target)
    elif args.cmd == "ask":
        cmd_ask(args.question)


if __name__ == "__main__":
    main()
