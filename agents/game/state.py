"""对局状态抽取、合并与行动约束。"""
import json
import logging
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, StringConstraints

import config
from rag.qa import get_client

logger = logging.getLogger(__name__)
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Quantity = Annotated[int, Field(strict=True, ge=0)]


class Action(BaseModel):
    name: Label
    costs: dict[Label, Quantity] = Field(default_factory=dict, max_length=8)
    available: bool | None = None


class GameState(BaseModel):
    mode: Label | None = None
    faction: Label | None = None
    version: Label | None = None
    turn: Label | None = None
    lineup: list[Label] = Field(default_factory=list, max_length=16)
    resources: dict[Label, Quantity] = Field(default_factory=dict, max_length=8)
    options: list[Action] = Field(default_factory=list, max_length=8)
    goal: Label | None = None
    last_action: Label | None = None


class TurnUpdate(BaseModel):
    reset: bool = False
    intent: Literal["recommend", "update", "guide"]
    patch: GameState


def update_game_state(question: str, previous: GameState) -> tuple[GameState, str, bool]:
    """抽取本轮明确陈述的变化。旧状态只用于消解本轮指代。"""
    if question.strip().rstrip("。！!").strip() in {"换一局", "新开一局", "重置对局", "开始新对局"}:
        return GameState(), "update", True

    prompt = (
        "你负责从用户最新输入提取游戏对局状态变化。旧状态仅用于消解指代。"
        "只返回 JSON 对象：{"
        '"reset":false,"intent":"recommend","patch":{"turn":"第4回合","resources":{"金币":3}}'
        "}。intent 为 recommend（求下一步建议）、update（仅汇报变化）或 guide（通用攻略）。"
        "用户明确换一局时 reset=true。patch 只能包含本轮用户明确确认的字段，"
        "不能从疑问、举例、条件假设或攻略知识中推断实际状态；没有变化用空对象。"
        "字段：mode 模式、faction 阵营、version 版本、turn 回合（字符串）、lineup 完整阵容（字符串数组）、"
        "resources 当前剩余资源（名称到非负整数）、options 当前备选动作数组，"
        '每个对象如 {"name":"升级","costs":{"金币":5},"available":true}。'
        "成本或可用性未知就省略，明确做不到用 available=false。"
        "goal 是目标，last_action 是用户已经做出的操作。"
        "用户明确说某字段未知或要清空时，标量用 null，数组用 []，资源用 {}。"
        "阵容有增删时结合旧阵容输出完整更新；options 如有变化，输出本轮更新后的完整列表。"
        "资源只输出本轮明确更新的绝对余量，不能把获得或消耗的数量当作余量。"
    )
    options = {}
    if urlsplit(config.DEEPSEEK_BASE_URL).hostname == "api.deepseek.com":
        options["response_format"] = {"type": "json_object"}
    try:
        response = get_client().chat.completions.create(
            model=config.DEEPSEEK_MODEL, temperature=0, max_tokens=800, stream=False,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({
                    "previous": previous.model_dump(), "latest": question,
                }, ensure_ascii=False)},
            ],
            **options,
        )
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise ValueError("对局状态输出被截断")
        raw = (choice.message.content or "").strip()
        if raw.startswith("```") and raw.endswith("```"):
            raw = raw.split("\n", 1)[-1][:-3].strip()
        update = TurnUpdate.model_validate_json(raw)
    except Exception as exc:
        logger.warning("对局状态解析失败：%s", type(exc).__name__)
        return previous, "recommend", False

    changes = update.patch.model_dump(exclude_unset=True)
    state = GameState() if update.reset else previous
    state_changed = any(key in changes and changes[key] != getattr(state, key)
                        for key in ("turn", "faction", "mode", "version"))
    if state_changed or changes.get("last_action"):
        # 新回合或实际行动后，旧资源与可选项可能失效。
        changes.setdefault("resources", {})
        changes.setdefault("options", [])
    elif changes.get("resources"):
        changes["resources"] = {**state.resources, **changes["resources"]}
    return GameState.model_validate({**state.model_dump(), **changes}), update.intent, True


def action_constraints(state: GameState) -> tuple[list[str], list[str], list[str]]:
    """只根据玩家明确提供的数量和限制判断，未知成本保持待确认。"""
    feasible, excluded, uncertain = [], [], []
    for action in state.options:
        shortages = [
            f"{resource}需 {cost}，现有 {state.resources[resource]}"
            for resource, cost in action.costs.items()
            if resource in state.resources and state.resources[resource] < cost
        ]
        if action.available is False:
            excluded.append(f"{action.name}（当前不可用）")
        elif shortages:
            excluded.append(f"{action.name}（{'、'.join(shortages)}）")
        elif action.available is not True and (
            not action.costs or any(resource not in state.resources for resource in action.costs)
        ):
            uncertain.append(action.name)
        else:
            feasible.append(action.name)
    return feasible, excluded, uncertain


def strategy_context(state: GameState) -> dict:
    feasible, excluded, uncertain = action_constraints(state)
    return {
        "玩家确认的状态": state.model_dump(exclude_none=True, exclude={"options"}),
        "用户给出了选项": bool(state.options),
        "可比较的选项": [option.model_dump(exclude_none=True) for option in state.options
                        if option.name in feasible or option.name in uncertain],
        "可以执行": feasible,
        "不可执行": excluded,
        "待确认": uncertain,
    }


def strategy_query(question: str, state: GameState, context: dict) -> str:
    """让追问也能带上当前模式、阵营和可选动作。"""
    parts = [state.mode, state.faction, state.version, state.turn,
             *[option["name"] for option in context["可比较的选项"]], state.goal]
    return " ".join(dict.fromkeys([*(part for part in parts if part and part not in question), question]))
