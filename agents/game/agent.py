"""编排对局状态更新、追问和基于证据的打法建议。"""

from collections.abc import Iterator
from typing import Protocol

from rag.answer_context import AnswerContext
from rag.answer_events import publish_answer, step

from .state import GameState, strategy_context, strategy_query, update_game_state


_GENERATION_INSTRUCTIONS = (
    "【对局建议】结合玩家当前状态和目标，给出首选动作、备选及何时改选。"
    "有用户给出的选项时，只在这些选项中选择。不可执行的动作只能解释为何排除。"
    "待确认动作只能作条件建议，不得假定资源足够。"
    "攻略机制附引用，结合本局的取舍标明「本局判断」，并说清依据。"
    "缺少会改变决定的信息时，只问一个关键问题；能分情况答则先给条件建议。"
)
_REVIEW_INSTRUCTIONS = (
    "对局状态由玩家提供，攻略片段用于支持游戏机制和经验，不要求片段复述玩家状态。"
    "允许明确标注的综合判断。若草稿推荐了不可执行的动作、把待确认的动作当成确定可行、"
    "或捏造资源、成本、机制，判 none。"
)


class AnswerStream(Protocol):
    def __call__(
        self, question: str, *, top_k: int | None, task_id: str, answer_context: AnswerContext | None,
    ) -> Iterator[dict]: ...


def stream_game_answer(
    question: str,
    previous: GameState,
    *,
    top_k: int | None,
    task_id: str,
    answer: AnswerStream,
    web_requested: bool = False,
) -> Iterator[dict]:
    yield step("game_state", "running", "正在核对当前对局与可选动作…")
    state, intent, parsed = update_game_state(question, previous)
    if not parsed:
        yield step("game_state", "warning", "没能确认本轮的对局变化")
        if web_requested:
            yield from answer(question, top_k=top_k, task_id=task_id, answer_context=None)
            return
        yield from publish_answer("这轮的对局状态没能确认。请重试，或用「回合、剩余资源、可选动作」的格式补充一下。", [])
        return

    yield {"event": "game_state", "data": state.model_dump()}
    yield step("game_state", "completed", "已核对当前对局")
    if intent == "update":
        message = ("已更新对局。你可以继续问下一步怎么选。"
                   if state.model_dump(exclude_defaults=True)
                   else "已清空上一局。告诉我这局的模式、当前回合或可选动作。")
        yield from publish_answer(message, [])
        return

    context = None
    if intent == "recommend":
        if not (state.turn or state.lineup or state.resources or state.options):
            if web_requested:
                yield step("game_state", "warning", "没有可用的对局状态，按通用问题查找攻略")
                yield from answer(question, top_k=top_k, task_id=task_id, answer_context=None)
                return
            yield from publish_answer("你现在有哪些可选操作？如果这些操作有资源消耗，也可以一起告诉我。", [])
            return
        strategy = strategy_context(state)
        if state.options and not (strategy["可以执行"] or strategy["待确认"]):
            excluded = "、".join(strategy["不可执行"])
            yield from publish_answer(f"按当前资源和限制，这些选项都做不了：{excluded}。还有其他可选操作吗？", [])
            return
        context = AnswerContext(
            retrieval_query=strategy_query(question, state, strategy),
            label="当前对局与行动约束",
            data=strategy,
            generation_instructions=_GENERATION_INSTRUCTIONS,
            review_instructions=_REVIEW_INSTRUCTIONS,
        )

    # 对局建议只依赖当前结构化状态，避免旧回合的聊天记录混入。
    yield from answer(question, top_k=top_k, task_id=task_id, answer_context=context)
