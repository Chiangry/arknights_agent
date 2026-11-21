"""同一个短片段跑本地 Whisper 和可选的 Gemini 或 Qwen，不写知识库。"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

import requests

import config
from ingest.bili_fetcher import parse_bvid
from ingest.transcribe import transcribe
from ingest.video_understanding import (
    DEFAULT_MODEL, MAX_CLIP_BYTES, QWEN_MODEL, check_clip, download_clip,
    extract_gemini, extract_qwen, qwen_endpoint,
)


def make_local_clip(file: Path, start: float, seconds: float, out: Path):
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", str(start),
        "-i", str(file.resolve()), "-t", str(seconds), "-map", "0:v:0", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "fast", "-b:v", "900k", "-maxrate", "1200k", "-bufsize", "2400k",
        "-c:a", "aac", "-b:a", "96k", "-fs", str(MAX_CLIP_BYTES), str(out),
    ], check=True, timeout=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bvid", help="B 站 BV 号或视频链接")
    source.add_argument("--file", type=Path, help="本地视频，不读取字幕轨")
    parser.add_argument("--start", type=float, default=0, help="样本起点（秒）")
    parser.add_argument("--seconds", type=float, default=45, help="样本长度（5–55 秒）")
    provider = parser.add_mutually_exclusive_group()
    provider.add_argument("--send-to-gemini", action="store_true", help="授权把当前样本发送给 Google Gemini API")
    provider.add_argument("--send-to-qwen", action="store_true", help="授权把当前样本发送给阿里云百炼")
    args = parser.parse_args()
    if not math.isfinite(args.start) or args.start < 0 or not 5 <= args.seconds <= 55:
        parser.error("起点须为非负数，样本长度须为 5–55 秒")
    bvid = parse_bvid(args.bvid) if args.bvid else None
    if args.bvid and not bvid:
        parser.error("无效 BV 号")
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if args.send_to_gemini and not key:
        parser.error("请先在本地 .env 中设置 GEMINI_API_KEY")
    model = os.getenv("GEMINI_VIDEO_MODEL", DEFAULT_MODEL)
    provider_name, extractor = ("gemini", lambda clip, dur: extract_gemini(clip, dur, key, model))
    if args.send_to_qwen:
        qwen_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not qwen_key:
            parser.error("请先在本地 .env 中设置 DASHSCOPE_API_KEY")
        try:
            endpoint = qwen_endpoint(os.getenv("DASHSCOPE_WORKSPACE_ID", "").strip(),
                                     os.getenv("DASHSCOPE_REGION", "cn-beijing").strip())
        except ValueError as exc:
            parser.error(str(exc))
        provider_name, model = "qwen", QWEN_MODEL
        extractor = lambda clip, dur: extract_qwen(clip, dur, qwen_key, endpoint)
    with TemporaryDirectory(prefix="video-asr-compare-") as tmp:
        folder = Path(tmp)
        if bvid:
            clip = download_clip(bvid, args.start, args.start + args.seconds, folder)
        else:
            clip = folder / "sample.mp4"
            make_local_clip(args.file, args.start, args.seconds, clip)
        duration = check_clip(clip, args.seconds)
        start = monotonic()
        segments = transcribe(str(clip))
        result = {"bvid": bvid, "sample_start_sec": args.start, "sample_duration_sec": duration,
                  "timestamps": "relative_to_sample", "whisper": {
                      "model": config.WHISPER_MODEL, "batch_size": config.WHISPER_BATCH_SIZE,
                      "elapsed_sec": round(monotonic() - start, 2),
                      "segments": [{"start_sec": a, "end_sec": b, "text": t} for a, b, t in segments],
                  }}
        if args.send_to_gemini or args.send_to_qwen:
            start = monotonic()
            try:
                result[provider_name] = {"model": model, **extractor(clip, duration),
                                         "elapsed_sec": round(monotonic() - start, 2)}
            except (ValueError, requests.RequestException) as exc:
                error = str(exc) if isinstance(exc, ValueError) else f"模型网络请求失败（{type(exc).__name__}）"
                result[provider_name] = {"model": model, "error": error}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
