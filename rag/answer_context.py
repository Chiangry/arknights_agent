"""领域 Agent 可传给共享问答流程的额外上下文。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnswerContext:
    """预设检索词与生成、核验所需的领域信息；答案仍针对原问题。"""

    retrieval_query: str
    label: str
    data: dict
    generation_instructions: str
    review_instructions: str
