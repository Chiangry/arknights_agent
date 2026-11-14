"""问答进度、答案及引用的共享事件格式。"""

import re


def step(stage: str, status: str, message: str) -> dict:
    return {"event": "agent_step", "data": {"stage": stage, "status": status, "message": message}}


def reference_numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\[引用([0-9]{1,6})\]", text)}


def answer_events(text: str, citations: list, *, replace: bool = False):
    if replace:
        yield {"event": "answer_replace", "data": {"text": text, "citations": citations}}
    else:
        yield {"event": "citations", "data": {"citations": citations}}
        yield {"event": "delta", "data": {"text": text}}


def publish_answer(text: str, citations: list, audio_videos: list | None = None, *, replace: bool = False):
    yield from answer_events(text, citations, replace=replace)
    yield from finish_answer(text, citations, audio_videos)


def finish_answer(text: str, citations: list, audio_videos: list | None = None):
    if audio_videos:
        references = {}
        for number in reference_numbers(text):
            if 1 <= number <= len(citations):
                cite = citations[number - 1]
                if cite["external"]:
                    references.setdefault(cite["video_id"], set()).add((cite["start"], cite["end"]))
        options = [
            {
                "bvid": video["bvid"], "title": video["title"], "author": video.get("author") or "",
                "citation_count": len(references.get(video["bvid"], ())),
            }
            for video in audio_videos
        ]
        options.sort(key=lambda option: option["citation_count"], reverse=True)
        yield {"event": "audio_import_offer", "data": {"videos": options}}
    yield {"event": "done", "data": {"citations": citations}}
