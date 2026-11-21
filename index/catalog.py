"""共享视频元数据与检索范围契约；未知归属保持为空。"""
from pydantic import BaseModel, ConfigDict, Field, model_validator

CATALOG = [
    {"id": "arknights", "label": "明日方舟", "categories": [
        {"id": "main", "label": "主线与活动"}, {"id": "roguelike", "label": "集成战略"},
        {"id": "cc", "label": "危机合约"}, {"id": "operator", "label": "干员测评"}]},
    {"id": "endfield", "label": "终末地", "categories": [
        {"id": "aic", "label": "集成工业产线"}, {"id": "exploration", "label": "探索与 Boss"},
        {"id": "combo", "label": "配队连携"}, {"id": "char", "label": "角色评测"}]},
]
GAMES = {g["id"]: g for g in CATALOG}
CATEGORIES = {c["id"]: g["id"] for g in CATALOG for c in g["categories"]}

_PREVIEW_RULES = {
    "endfield": (
        ("aic", ("工业产线", "集成工业", "产线", "工厂蓝图", "配平")),
        ("combo", ("配队", "连携", "破韧轴", "配装轴", "轮椅轴")),
        ("exploration", ("探索", "宝箱", "地图路线", "boss", "首领")),
        ("char", ("角色评测", "养成", "抽取", "武器测评", "技能解析")),
    ),
    "arknights": (
        ("roguelike", ("集成战略", "肉鸽", "黑流树海")),
        ("cc", ("危机合约",)),
        ("operator", ("干员测评", "模组评测", "抽取建议", "干员解析")),
        ("main", ("主线", "活动关卡", "卫戍协议", "磨难")),
    ),
}


def suggest_video_category(title: str | None, description: str | None) -> dict:
    """轻量预览建议。标题优先，不确定时保持未分类，由用户确认。"""
    title = (title or "").casefold()
    description = (description or "").casefold()
    game_id = None
    for text in (title, description):
        if "终末地" in text or "endfield" in text:
            game_id = "endfield"
            break
        if any(word in text for word in ("明日方舟", "arknights", "卫戍协议", "黑流树海")):
            game_id = "arknights"
            break
    category_id = None
    if game_id:
        for text in (title, description):
            category_id = next((category for category, terms in _PREVIEW_RULES[game_id]
                                if any(term in text for term in terms)), None)
            if category_id:
                break
    return {"game_id": game_id, "category_id": category_id}


class RetrievalScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: str | None = None
    category_id: str | None = None
    video_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.game_id is not None and self.game_id not in GAMES:
            raise ValueError("未知游戏")
        if self.category_id is not None:
            if self.category_id not in CATEGORIES:
                raise ValueError("未知分类")
            if self.game_id and CATEGORIES[self.category_id] != self.game_id:
                raise ValueError("分类不属于所选游戏")
        return self

    @property
    def restricted(self):
        return bool(self.game_id or self.category_id or self.video_ids)


class VideoMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, max_length=300)
    author: str | None = Field(default=None, max_length=200)
    game_id: str | None = None
    category_id: str | None = None
    stage_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_metadata(self):
        RetrievalScope(game_id=self.game_id, category_id=self.category_id)
        if self.category_id and not self.game_id:
            raise ValueError("选择分类时必须指定游戏")
        if "title" in self.model_fields_set and not self.title:
            raise ValueError("标题不能为空")
        return self
