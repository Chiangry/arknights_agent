"""已确认的攻略术语，只扩展检索，不改写引用正文。"""
import re
from dataclasses import dataclass

from index.catalog import CATEGORIES, RetrievalScope
from text_normalization import to_simplified


@dataclass(frozen=True)
class QuerySignals:
    game_id: str
    entity: str
    attribute: str
    evidence_pattern: str
    alias: str = ""

    def expand(self, question: str) -> str:
        return question if self.entity in question or not self.alias else f"{question} {self.entity}"


def query_signals(question: str, scope: RetrievalScope | None = None) -> QuerySignals | None:
    question = to_simplified(question)
    game = (scope.game_id or CATEGORIES.get(scope.category_id)) if scope else None
    if game != "arknights" and re.search(r"夜明河|(?<!夜)明河(?=\s*(?:的|怎么|如何|用什么|配队|组队|种族|是(?:什么|哪|啥)))", question):
        alias = "" if "夜明河" in question else "明河"
        if "种族" in question:
            # 需要陈述型写法；标题或「种族是什么」不是种族证据。
            return QuerySignals("endfield", "夜明河", "种族",
                                r"夜明河[ \t]*(的|[，,、])?[ \t]*种族[ \t]*(是|为|[:：])[ \t]*[^什哪何谁？?为何[:space:]，。；：:]", alias)
        if re.search(r"配队|组队|队友|阵容|搭配", question):
            return QuerySignals("endfield", "夜明河", "配队", r"配队|组队|队友|阵容|搭配|带上|替换", alias)
    if game != "endfield" and "卫戍协议" in question and "乌萨斯" in question and re.search(
        r"怎么玩|攻略|打法|怎么打|开局|运营|怎么选", question,
    ):
        return QuerySignals("arknights", "乌萨斯", "打法", r"开局|优先|选择|部署|运营|先.{0,24}再")
    return None
