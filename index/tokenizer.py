"""中文分词：为全文检索(tsvector/tsquery)提供分词。入库时对 chunk 分词，查询时对问题分词。"""
import jieba

# 中文停用词：无检索价值的虚词/疑问词。注意 jieba 会把"什么/怎么"切成独立词，
# 因此必须把它们作为独立的 2 字词列出，不能用"没什么/有什么"这类粘连串。
STOP = set("""
什么 怎么 怎么样 如何 为何 为啥 为什么 多少 几个 几种 哪些 哪个 哪 这 那 这里 那里
这个 那个 一种 一点 一些 一下 一步
的 了 是 有 没 吗 呢 么 吧 啊 呀 哦 在 就 也 还 和 与 或 个 都 会 要 去 能 可以
自己 我们 你们 他们 大家 他 她 它 用 看 想 知道 应该 该 应当 需要 请 帮 我 讲 给 说明
事情 区别 作用 好处 干嘛 有关 关于 因为 所以 但是 还是 然后
""".split())


def cut(text: str):
    """返回去停用词后的词列表（过滤单字）。"""
    return [w for w in jieba.cut(text) if w.strip() and len(w) > 1 and w not in STOP]


def tokenize(text: str) -> str:
    """chunk 文本 -> 空格分隔的分词串，供 to_tsvector('simple', tokens) 建全文索引。"""
    return " ".join(cut(text))


def query_terms(text: str) -> str:
    """问题 -> 空格分隔分词，供 to_tsquery('simple', ...)。"""
    return " ".join(cut(text))
