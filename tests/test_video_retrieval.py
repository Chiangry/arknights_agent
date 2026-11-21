from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from app import services
from index.catalog import RetrievalScope
from rag import retriever, video_retrieval


ROWS = [
    {"video_id": "one", "author": "某攻略作者", "title": "明河实战配队全解析", "eligible": True,
     "published_at": datetime(2026, 10, 31, 17, tzinfo=timezone.utc)},
    {"video_id": "other", "author": "其他作者", "title": "配队攻略", "eligible": True},
]


class VideoRetrievalTests(TestCase):
    def test_author_removed_from_subtitle_query(self):
        plan = video_retrieval.match_videos("某攻略作者的配队", "某攻略作者的配队", None, ROWS)
        self.assertEqual(plan.scope.video_ids, ["one"])
        self.assertEqual(plan.query, "配队")

    def test_explicit_title_and_date(self):
        q = "《明河实战配队全解析》里怎么搭配"
        self.assertEqual(video_retrieval.match_videos(q, q, None, ROWS).scope.video_ids, ["one"])
        q = "2026年11月发布的配队"
        plan = video_retrieval.match_videos(q, q, None, ROWS)
        self.assertEqual(plan.scope.video_ids, ["one"])
        self.assertEqual(plan.query, "配队")

    def test_partial_title_is_a_hint_not_a_filter(self):
        q = "明河配队"
        plan = video_retrieval.match_videos(q, q, None, ROWS)
        self.assertIsNone(plan.scope)
        self.assertIn("one", plan.hints)

    def test_author_filter_respects_video_scope(self):
        q = "某攻略作者的配队"
        scope = RetrievalScope(video_ids=["other"])
        rows = [{**r, "eligible": r["video_id"] == "other"} for r in ROWS]
        self.assertTrue(video_retrieval.match_videos(q, q, scope, rows).blocked)

    def test_stream_keeps_author_query_and_does_not_substitute_other_sources(self):
        q = "某攻略作者的配队"
        with patch.object(video_retrieval, "retrieval_video_catalog", return_value=ROWS), \
             patch.object(services, "retrieve_with_status", return_value=([], "insufficient", "无片段")) as retrieve, \
             patch.object(services, "search_bili_videos") as external:
            events = list(services.stream_answer(q))
        self.assertEqual(retrieve.call_args.args[0], "配队")
        self.assertEqual(retrieve.call_args.kwargs["scope"].video_ids, ["one"])
        self.assertEqual(retrieve.call_args.kwargs["ranking_question"], q)
        self.assertTrue(any("找到 1 部" in str(e) for e in events))
        external.assert_not_called()

    def test_rerank_receives_author_and_original_subtitle(self):
        hit = {"text": "明河带两位辅助", "distance": 0.2,
               "meta": {"video_id": "one", "chunk_idx": 0, "author": "某攻略作者", "title": "明河实战"}}
        with patch.object(retriever.config, "RERANK_ENABLED", True), \
             patch.object(retriever, "embed_texts", return_value=[[1.0]]), \
             patch.object(retriever, "hybrid_search", return_value=[hit]), \
             patch.object(retriever, "rerank_scores", return_value=[1.0]) as rerank, \
             patch.object(retriever, "expand_neighbors", side_effect=lambda hits, _: hits):
            returned = retriever.retrieve("配队")
        self.assertIn("作者：某攻略作者", rerank.call_args.args[1][0])
        self.assertEqual(returned[0]["text"], "明河带两位辅助")
