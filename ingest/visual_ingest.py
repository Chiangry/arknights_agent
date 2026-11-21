"""用户授权的短片段解析；无画面证据才尝试同段口述转写。"""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import requests
from faster_whisper.audio import decode_audio
from faster_whisper.vad import VadOptions, get_speech_timestamps
import config

from ingest.chunker import build_chunks
from ingest.name_correction import VISUAL_CAPTION, VISUAL_CARD, WHISPER_LOCAL
from ingest.transcribe import transcribe
from ingest.video_understanding import check_clip, download_clip, extract_qwen, qwen_endpoint
from text_normalization import to_simplified


@dataclass(frozen=True)
class VisualRange:
    start: float
    seconds: float


class NoUsableEvidence(ValueError):
    """已检查该区间，但没有足够的可入库内容。"""


def full_video_ranges(duration: float) -> list[VisualRange]:
    if not math.isfinite(duration) or not 0 < duration <= 28800:
        raise ValueError("无法确认有效的视频时长，未启动全片解析")
    ranges = []
    start = 0.0
    while start < duration:
        remaining = duration - start
        seconds = remaining if remaining < 50 else 45.0
        ranges.append(VisualRange(start, seconds))
        start += seconds
    return ranges


def qwen_config():
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise ValueError("未配置百炼 DASHSCOPE_API_KEY")
    return key, qwen_endpoint(os.getenv("DASHSCOPE_WORKSPACE_ID", "").strip(),
                              os.getenv("DASHSCOPE_REGION", "cn-beijing").strip())


def make_visual_clip(src: Path, dst: Path):
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                              text=True, check=True, timeout=10).stdout
    if "libx264" in encoders:
        codec = ["-c:v", "libx264", "-preset", "fast", "-maxrate", "450k", "-bufsize", "900k"]
    elif "h264_videotoolbox" in encoders:
        codec = ["-c:v", "h264_videotoolbox"]
    else:
        codec = ["-c:v", "copy"]
    output = ["-vf", "fps=4", "-b:v", "300k", "-pix_fmt", "yuv420p"] if codec[-1] != "copy" else []
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(src), "-map", "0:v:0",
                    "-an", *output, *codec, "-fs", "7499000", str(dst)],
                   check=True, timeout=75, capture_output=True)


def scan_text(src: Path, folder: Path):
    """本地稀疏检测；游戏 HUD 可能命中，因此结果只作进度提示。"""
    if sys.platform != "darwin" or not shutil.which("swift"):
        return None
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(src), "-vf", "fps=1/4",
                        "-frames:v", "14", str(folder / "frame-%03d.jpg")], check=True,
                       timeout=25, capture_output=True)
        frames = sorted(folder.glob("frame-*.jpg"))
        if not frames:
            return False
        script = Path(__file__).with_name("scan_frame_text.swift")
        # 缓存里只有编译产物，不存每次任务的媒体或识别内容。
        modules = config.DATA_DIR / "swift-ocr-module-cache"
        modules.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["swift", "-module-cache-path", str(modules),
                                 str(script), *map(str, frames)], check=True,
                                capture_output=True, text=True, timeout=55)
        return {"found": True, "not-found": False}.get(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def visual_chunks(report: dict, start: float) -> list[dict]:
    chunks = []
    seen = set()
    for fact in sorted(report["facts"], key=lambda f: (f["start_sec"], f["end_sec"])):
        is_caption = fact["kind"] == "subtitle"
        source = VISUAL_CAPTION if is_caption else VISUAL_CARD
        evidence = to_simplified(fact["evidence"].strip())
        text = evidence if is_caption else (
            f"画面原文或线索：{evidence}\n模型解读：{to_simplified(fact['claim'].strip())}"
        )
        key = (source, evidence, round(fact["start_sec"], 1))
        if key in seen:
            continue
        seen.add(key)
        chunks.append({"start": start + fact["start_sec"], "end": start + fact["end_sec"],
                       "text": text, "evidence_source": source})
    return chunks


def _recommendation(has_text) -> str:
    return {True: "抽样发现可读文字，可能包含硬字幕或攻略卡",
            False: "抽样未发现明显文字，仍可尝试识别画面里的配队或操作",
            None: "本地文字探测不可用，按时间抽样推荐"}[has_text]


def sample_ranges(duration: float) -> list[VisualRange]:
    seconds = min(45.0, duration) if duration > 0 else 45.0
    ranges = [VisualRange(0, seconds)]
    if duration >= seconds * 2:
        ranges.append(VisualRange(min(round(duration * 0.45), duration - seconds), seconds))
    return ranges


def get_visual_or_audio_chunks(bvid: str, selected: VisualRange | None, progress, *,
                               duration: float = 0, confirm=None, task_id: str | None = None,
                               whole_video: bool = False, has_api_subtitles: bool = False) -> list[dict]:
    # 自动路线必须经由推荐片段后的授权回调，不能把 None 当成默认同意。
    if selected is None and confirm is None:
        raise ValueError("自动画面解析缺少授权流程")
    with TemporaryDirectory(prefix="visual-ingest-") as tmp:
        root = Path(tmp)
        candidates = [selected] if selected else sample_ranges(duration)
        best = None
        for i, candidate in enumerate(candidates):
            folder = root / str(i)
            folder.mkdir()
            progress(10 + i * 8, "正在本地截取短片段并抽样检查画面…")
            try:
                clip = download_clip(bvid, candidate.start, candidate.start + candidate.seconds,
                                     folder, prefer_avc=True)
                check_clip(clip, candidate.seconds, require_audio=False)
                has_text = None if whole_video else scan_text(clip, folder)
            except Exception:
                if selected is not None or (i == len(candidates) - 1 and not best):
                    raise
                continue
            if best is None or has_text:
                best = (candidate, clip, folder, has_text)
            if has_text or (has_text is None and not selected):
                break
        if best is None:
            raise RuntimeError("没有取得可供抽样的片段")
        selected, clip, folder, has_text = best
        reason = _recommendation(has_text)
        key, endpoint = qwen_config()
        if confirm is not None:
            progress(30, reason)
            decision = confirm(selected, reason)
            if decision != "approved":
                raise ValueError("未确认上传，任务已结束" if decision == "expired" else "已跳过上传，未更改已有切片")
        progress(32, "正在准备本段静音画面…" if whole_video else reason + "；正在准备静音画面供 Qwen 复核…")
        video = folder / "visual.mp4"
        make_visual_clip(clip, video)
        duration = check_clip(video, selected.seconds, require_audio=False)
        progress(39, "正在用 Qwen 解析所选片段的硬字幕和攻略画面…")
        try:
            report = extract_qwen(video, duration, key, endpoint, visual_only=True, task_id=task_id)
        except requests.RequestException as exc:
            raise RuntimeError(f"百炼请求失败（{type(exc).__name__}），未切换到整段转写") from None
        chunks = visual_chunks(report, selected.start)
        if whole_video:
            end_limit = selected.start + selected.seconds
            chunks = [{**chunk, "end": min(chunk["end"], end_limit)} for chunk in chunks if chunk["start"] < end_limit]
        # 全片模式里，配队卡等静态画面不代表口述已被覆盖；有硬字幕则优先用可见正文。
        if has_api_subtitles:
            progress(52, "本段口述已有 API 字幕，仅保留画面解析结果")
            return chunks
        if chunks and (not whole_video or _subtitles_cover_window(report, duration)):
            progress(52, f"已提取 {len(chunks)} 条画面证据，本片段跳过 Whisper")
            return chunks

        progress(47, "本段没有硬字幕，正在检测是否有人声…")
        audio = folder / "selected.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(clip), "-vn",
                        "-ar", "16000", "-ac", "1", str(audio)], capture_output=True, timeout=20)
        if not audio.is_file() or audio.stat().st_size <= 44:
            if chunks:
                return chunks
            raise NoUsableEvidence("本段没有可用画面证据，也没有可用音轨")
        voice = get_speech_timestamps(decode_audio(str(audio)), VadOptions())
        if sum(s["end"] - s["start"] for s in voice) < 16000:
            if chunks:
                return chunks
            raise NoUsableEvidence("本段未提取到攻略画面，也未检测到足够人声")
        progress(52, "检测到可能的人声，仅对所选片段回退到 Whisper…")
        segments = transcribe(str(audio), on_progress=lambda *_: progress(53, "正在转写所选片段…"))
        if len(re.findall(r"[\w\u4e00-\u9fff]", "".join(s[2] for s in segments))) < 12:
            if chunks:
                return chunks
            raise NoUsableEvidence("本段转写结果过于稀疏，未入库")
        speech_chunks = build_chunks([(a + selected.start, min(b, selected.seconds) + selected.start, t)
                                      for a, b, t in segments if a < selected.seconds])
        return chunks + [{**chunk, "evidence_source": WHISPER_LOCAL} for chunk in speech_chunks]


def _subtitles_cover_window(report: dict, duration: float) -> bool:
    """零星的一条硬字幕不能代替整段口述。按不重叠的时间覆盖保守判定。"""
    end = covered = 0.0
    captions = sorted((f["start_sec"], f["end_sec"]) for f in report["facts"] if f["kind"] == "subtitle")
    for start, stop in captions:
        covered += max(0, stop - max(start, end))
        end = max(end, stop)
    return covered >= 0.65 * duration
