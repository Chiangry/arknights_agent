"""保守地用同视频可读文字校对 Whisper 中的角色专名。"""
import re
from collections import defaultdict
from functools import lru_cache

from pypinyin import lazy_pinyin

from text_normalization import to_simplified

VISUAL_CAPTION = "画面硬字幕（Qwen 识读）"
VISUAL_CARD = "攻略画面（Qwen 解读）"
WHISPER_LOCAL = "口述证据（Whisper 局部转写）"
TRUSTED_VISUAL_SOURCES = (VISUAL_CAPTION, VISUAL_CARD)
_ATTRIBUTES = r"原型|种族|职业|技能|天赋|档案|配队|装备|立绘"
_TITLE_NAME = re.compile(rf"(?:^|[：:？?！!，,。｜|、\s「《【])([\u3400-\u9fff]{{3,5}})(?=的(?:{_ATTRIBUTES}))")
_ATTRIBUTE_MENTION = re.compile(rf"(?:的)?(?:{_ATTRIBUTES})")
_HAN_NAME = re.compile(r"[\u3400-\u9fff]{3,5}")


@lru_cache(maxsize=4096)
def _pronunciation(word: str) -> tuple[str, ...]:
    return tuple(lazy_pinyin(word))


class VideoNameCorrection:
    def __init__(self, title: str):
        self.names = {m[1] for m in _TITLE_NAME.finditer(to_simplified(title))}
        self.confirmed = set()
        self.reference_texts = []

    def observe(self, text: str) -> None:
        if self.names and text:
            text = to_simplified(text)
            self.reference_texts.append(text)
            self.confirmed.update(name for name in self.names if name in text)

    def observe_chunks(self, chunks) -> None:
        for chunk in chunks:
            if chunk["evidence_source"] in TRUSTED_VISUAL_SOURCES:
                # 模型的解读不算画面原字；只采用记录的屏幕文字或硬字幕。
                self.observe(chunk["text"].split("\n模型解读：", 1)[0])

    def correct(self, chunks: list[dict]) -> list[dict]:
        if not self.confirmed:
            return chunks
        by_sound = defaultdict(set)
        for name in self.names:
            by_sound[_pronunciation(name)].add(name)
        sizes = {len(name) for name in self.confirmed}
        output = []
        for chunk in chunks:
            original = chunk["text"]
            if chunk["evidence_source"] != WHISPER_LOCAL:
                output.append(chunk)
                continue
            edits = []
            for mention in _ATTRIBUTE_MENTION.finditer(original):
                end = mention.start()
                matches = []
                for size in sizes:
                    start = end - size
                    wrong = original[start:end] if start >= 0 else ""
                    if not _HAN_NAME.fullmatch(wrong):
                        continue
                    alternatives = by_sound.get(_pronunciation(wrong), ())
                    if len(alternatives) != 1 or wrong in alternatives:
                        continue
                    name = next(iter(alternatives))
                    if name not in self.confirmed or len(name) != len(wrong):
                        continue
                    if not any(a == b for a, b in zip(wrong, name)):
                        continue
                    if any(wrong in text for text in self.reference_texts):
                        continue
                    matches.append((start, end, name))
                if len(matches) == 1 and (not edits or matches[0][0] >= edits[-1][1]):
                    edits.append(matches[0])
            corrected = original
            for start, end, name in reversed(edits):
                corrected = corrected[:start] + name + corrected[end:]
            output.append({**chunk, "text": corrected, "original_text": original} if edits else chunk)
        return output
