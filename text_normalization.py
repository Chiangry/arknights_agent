"""本地统一中文正文和检索词的字形，不做专名或同音词纠正。"""

from opencc import OpenCC

_traditional_to_simplified = OpenCC("t2s")


def to_simplified(text: str) -> str:
    return _traditional_to_simplified.convert(text)
