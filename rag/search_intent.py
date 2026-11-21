"""外部检索授权只来自当前用户消息或本次开关，不读历史/改写结果。"""
import re
from dataclasses import dataclass


_BILI = r"(?i:b\s*站|哔哩哔哩|(?:www\.)?bilibili(?:\.com)?)"
_OTHER = r"百度|谷歌|(?i:google|bing|youtube)|知乎|小红书|抖音|微博|必应|维基百科|百科|[\w-]+(?:\.[\w-]+)+"
_VERB = r"(?:搜索|检索|搜(?:一?下|一搜)?|查找|查(?:一?下|一查)?|找(?:一?下|一找)?)"
_SITE = rf"(?:{_BILI}|{_OTHER})"
_DIRECT = re.compile(
    rf"(?P<only>只(?:在|去|到|用|从)?|仅(?:在|去|到|用|从)?|不要查本地[，, ]*只在)?"
    rf"(?:去|到|在|从|用|上)?\s*(?P<site>{_SITE})(?:\s*上)?\s*(?:帮我|给我)?\s*{_VERB}"
)
_REVERSE = re.compile(rf"(?P<only>只|仅)?{_VERB}\s*(?:去|到|在|从|用)?\s*(?P<site>{_SITE})")
_EXPLICIT_OTHER = re.compile(
    rf"(?P<only>只|仅)?(?:去|在|到|从)\s*(?P<site>[\u4e00-\u9fff]{{2,10}}?)(?:上)?\s*(?:帮我)?\s*{_VERB}"
)
_GENERIC = re.compile(rf"(?:帮我|请|^|[，,。；;])\s*(?:打开)?(?:联网|上网)\s*{_VERB}")
_NEGATIVE = re.compile(rf"(?:不(?:要|用|必)|别|禁止)\s*(?:再)?\s*(?:联网|上网|(?:去|到|在|用)?\s*{_SITE}\s*(?:上)?\s*{_VERB}|{_VERB}\s*{_SITE})")
_QUOTED = re.compile(r"「[^」]*」|“[^”]*”|『[^』]*』|《[^》]*》|`[^`]*`|\"[^\"]*\"")
_HYPOTHETICAL = re.compile(r"如果|假如|假设|例如|比如|举例|提到|叫做|关键词是|会不会|能否识别")


@dataclass(frozen=True)
class SearchIntent:
    local: bool = True
    source: str | None = None
    unsupported: str | None = None
    subject: str = ""


def search_intent(question: str, enabled: bool = False) -> SearchIntent:
    visible = _QUOTED.sub(lambda m: " " * len(m[0]), question)
    if _NEGATIVE.search(visible):
        return SearchIntent(subject=question)
    if re.match(r"\s*(?:只|仅)(?:查|搜|用|检索)?\s*(?:本地|知识库)", visible):
        return SearchIntent(subject=question)
    match = next((m for pattern in (_DIRECT, _REVERSE, _EXPLICIT_OTHER) if (m := pattern.search(visible))), None)
    if match and not _HYPOTHETICAL.search(visible[:match.start()]) and not re.match(
        r"\s*(?:是[什指]|是什么|功能|结果会|怎么用)", visible[match.end():],
    ):
        site = match["site"]
        if site in {"本地", "本地库", "知识库", "本地知识库", "视频库"}:
            return SearchIntent(subject=question)
        only = bool(match["only"]) or bool(re.search(r"不(?:要|用)查本地", visible))
        subject = (question[:match.start()] + " " + question[match.end():]).strip(" ，,：:。！？?")
        subject = re.sub(r"^(?:请|麻烦|帮我|给我)[\s，,]*", "", subject).strip()
        subject = re.sub(r"^(?:上的|上|的)\s*", "", subject)
        if re.fullmatch(_BILI, site):
            return SearchIntent(not only, "bilibili", subject=subject)
        return SearchIntent(not only, unsupported=site, subject=subject)
    if enabled or _GENERIC.search(visible):
        return SearchIntent(source="bilibili", subject=question)
    return SearchIntent(subject=question)
