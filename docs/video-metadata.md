# 视频档案与范围检索

## 升级

先备份 PostgreSQL，再在项目根目录运行：

```sh
python -m scripts.migrate_video_metadata
```

迁移是事务性的、可重复执行，只扩展既有 `videos` 表并回填平台/地址/入库时间。
不会重新下载、转写、改写切片/向量，也不会猜测历史视频的游戏分类。
新数据库使用更新后的 `deploy/init.sql`。

## 数据约定

- `video_id` 继续沿用 BV 号或本地内容哈希，切片仍以它关联。
- `source` 保留原来的字幕来源含义；`source_platform` 才是 `bilibili/local`。
- `published_at` 是平台发布时间，未知为空；`indexed_at` 是入库时间。
- `duration_seconds` 是平台时长，缺失时列表以最大字幕结束时间作为估计。
- `game_id/category_id/stage_name` 可为空；归属和分类由用户确认，不自动归为明日方舟。
- `chunk_count` API 返回实际切片计数。零切片档案代表尚未完成入库，不影响已有去重检查。
- 摘要、画面识别仍未实现，新增列留空，不显示模拟内容。
- 平台补全只填空值；重新索引不覆盖非空人工标题、作者与分类。

## 接口

- `GET /api/catalog`：游戏及分类的唯一业务定义，前端共享。
- `GET /api/video-metadata?url=...`：预读 B 站标题等，不下载媒体。
  预览同时返回作品和分区建议（可为空）；链接框回车只触发预览，手动点击解析后才提交用户编辑过的档案。
- `POST /api/videos`：原表单新增 `metadata` JSON 字符串；省略仍兼容。
- `GET /api/videos`：支持 `game_id/category_id/query/limit/offset`；省略分页保持旧客户端兼容。
- `GET/PATCH /api/videos/{id}`：读取/修改档案。PATCH 省略保持原值，显式 null 清除可空字段；切换游戏需同时清除或选择对应分类。
- `GET /api/videos/{id}/chunks`：按时间分页读取实际入库切片，可传 `query` 做正文包含匹配；不走向量检索或相邻片段合并。
- `DELETE /api/videos/{id}`：永久删除已入库档案及其切片和向量。正在解析的视频返回 409；不删除来源媒体、聊天记录或临时转写缓存。非默认前端地址可通过 `VIDEO_DELETE_ORIGINS` 配置浏览器来源。
- `POST /api/videos/{id}/refresh-metadata`：按需补全平台信息，不转写。
- `POST /api/ask`：新增 `scope: {game_id, category_id, video_ids}`。

检索条件取交集，在向量/全文两路召回 LIMIT 前同时生效；普通问答和 Agent 共用。
限定范围证据不足时保留可确认内容并提示扩大范围，不自动跳到全库/B站。
用户清除所有筛选后重新提问，恢复原有 B 站补查/转写确认流程。
范围随聊天记录保存在浏览器，切换对话不串用范围；游戏未知视频仅在不限定游戏时召回。

问答会先在已入库的视频档案中匹配明确提及的作者、完整标题，以及
“2026年11月发布”这类时间条件，然后在符合条件的视频中检索字幕。
标题、简介和关卡的词项匹配还会补充候选，不取代常规字幕召回。
标题、作者、发布时间和关卡提供来源上下文，不能替代配队或操作的字幕证据；
限定来源时不会自动用其他作者或 B 站结果代答。标签和用户备注暂未接入。
现有切片与向量不需要重建。

## 验证

```sh
python -m unittest discover -s tests -v
RUN_PG_TESTS=1 python -m unittest discover -s tests -v
```

第二条需已迁移的本地数据库。集成测试所有档案和向量写入在事务末尾回滚，不残留测试视频。
