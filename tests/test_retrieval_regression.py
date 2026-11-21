from unittest import TestCase
from unittest.mock import Mock, patch

from app import services
from index.catalog import RetrievalScope
from rag import retriever
from rag.query_signals import query_signals
from rag.video_retrieval import VideoPlan, match_videos


def chunk(vid, idx, text, distance=0.58):
    return {"text": text, "distance": distance,
            "meta": {"video_id": vid, "chunk_idx": idx, "start": 315, "end": 360}}


class RetrievalRegressions(TestCase):
    def test_species_evidence_beats_name_only_and_trace_shows_filter(self):
        q = "明河的种族是什么"
        direct = chunk("BV1FTsE6UEai", 60, "夜明河种族为龙")
        name_only = chunk("BV1FTsE6UEai", 1, "我们来聊聊夜明河")
        filtered = chunk("other", 0, "银河的另一种名字")
        trace = Mock()
        with (
            patch.object(retriever.config, "RERANK_ENABLED", True),
            patch.object(retriever, "embed_texts", return_value=[[1.0]]) as embed,
            patch.object(retriever, "hybrid_search", return_value=[name_only, filtered]),
            patch.object(retriever, "attribute_search", return_value=[direct]) as attribute,
            patch.object(retriever, "rerank_scores", return_value=[0.98, 0.0, 0.3]),
            patch.object(retriever, "expand_neighbors", side_effect=lambda hits, _: hits),
        ):
            hits, status, _ = retriever.retrieve_with_status(q, top_k=1, trace=trace)
        self.assertEqual((hits[0]["meta"]["chunk_idx"], status), (60, "sufficient"))
        embed.assert_called_once_with([q + " 夜明河"])
        self.assertEqual(attribute.call_args.args[1], "夜明河")
        ranking = next(call.kwargs["candidates"] for call in trace.call_args_list if call.args == ("ranking",))
        self.assertEqual([row["decision"] for row in ranking], ["top_k", "selected", "below_threshold"])

    def test_requested_author_keeps_attribute_search_scoped(self):
        q = "萧然Q的明河配队是什么"
        plan = match_videos(q, q, None, [
            {"eligible": True, "author": "萧然Q", "video_id": "author_video"},
            {"eligible": True, "author": "其他作者", "video_id": "other"},
        ])
        signal = query_signals(plan.query, plan.scope)
        self.assertEqual((plan.scope.video_ids, signal.entity, signal.attribute), (["author_video"], "夜明河", "配队"))
        with (patch.object(retriever, "embed_texts", return_value=[[1]]),
              patch.object(retriever, "hybrid_search", return_value=[]),
              patch.object(retriever, "attribute_search", return_value=[]) as attribute):
            retriever.retrieve(plan.query, scope=plan.scope)
        self.assertEqual(attribute.call_args.kwargs["scope"].video_ids, ["author_video"])

    def test_how_to_ask_is_not_a_species_alias_or_claim(self):
        q = "卫戍协议乌萨斯怎么玩"
        signal = query_signals(q)
        self.assertEqual((signal.entity, signal.attribute, signal.game_id), ("乌萨斯", "打法", "arknights"))
        self.assertIsNone(query_signals("明河和银河有什么关系"))
        self.assertIsNone(query_signals("明河的种族是什么", RetrievalScope(game_id="arknights")))
        self.assertIsNone(query_signals("叶铭河的种族是什么"))
        self.assertEqual(query_signals("明河是什么种族").entity, "夜明河")

    def test_live_diagnostics_log_coverage_and_draft_verdict(self):
        q = "明河的种族是什么"
        hit = chunk("BV1FTsE6UEai", 60, "夜明河种族为龙")
        full = {"verdict": "full", "intent": "种族", "reason": "直接说明了种族", "covered": ["种族"], "missing": []}
        with (
            patch.object(services.config, "RAG_RETRIEVAL_DIAGNOSTICS", True),
            patch.object(services, "plan_video_retrieval", return_value=VideoPlan(None, q)),
            patch.object(services, "retrieve_with_status", return_value=([hit], "sufficient", "命中")) as retrieve,
            patch.object(services, "_context_answerability", return_value=full),
            patch.object(services, "_generate_answer", return_value="是龙。[引用1]"),
            patch.object(services, "_review_draft", return_value=full),
            self.assertLogs("uvicorn.error.rag", "INFO") as logs,
        ):
            list(services.stream_answer(q, task_id="case"))
        self.assertTrue(callable(retrieve.call_args.kwargs["trace"]))
        for marker in ('"task_id": "case"', '"stage": "answer_check"', '"stage": "answer_review"'):
            self.assertIn(marker, "\n".join(logs.output))
