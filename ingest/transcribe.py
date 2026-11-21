"""语音转文字：用 faster-whisper 将视频/音频转成带时间戳的文本片段。"""
import config
from faster_whisper import BatchedInferencePipeline, WhisperModel
from text_normalization import to_simplified

_model = None


def get_model():
    global _model
    if _model is None:
        _model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
    return _model


def transcribe(video_path: str, on_progress=None) -> list:
    """
    转写视频，返回片段列表，每项为 (start, end, text)，单位为秒。
    vad_filter 用于过滤静音，减少空转写。

    on_progress(done_seconds, total_seconds)：faster-whisper 是流式产出片段的，
    每产出一段就回调一次。批量模式下，同批片段会在该批推理完成后陆续产出。
    """
    model = get_model()
    options = {"language": config.WHISPER_LANGUAGE, "vad_filter": True}
    if config.WHISPER_BATCH_SIZE > 0:
        # 推理管线有请求内状态。每次创建管线，底层模型仍跨请求复用。
        pipeline = BatchedInferencePipeline(model=model)
        segments, info = pipeline.transcribe(
            video_path, batch_size=config.WHISPER_BATCH_SIZE,
            without_timestamps=False, **options,
        )
    else:
        segments, info = model.transcribe(video_path, **options)
    total = float(getattr(info, "duration", 0) or 0)
    result = []
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            result.append((seg.start, seg.end, to_simplified(text)))
        if on_progress:
            done = float(seg.end)
            on_progress(min(done, total) if total > 0 else done, total)
    if on_progress and total > 0:
        on_progress(total, total)
    return result
