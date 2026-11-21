from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import services
from app.main import app
from agents.game import GameState
from rag.search_intent import search_intent


def coverage(verdict):
    return {"verdict": verdict, "reason": "测试核验", "covered": [], "missing": []}


class SearchIntentTests(TestCase):
    def test_only_explicit_commands_authorize_web(self):
        for q in ("B站上有这个角色的视频吗", "B站搜索是什么", "例如去B站搜明河是什么意思",
                  "“去B站搜明河”这句话怎么翻译", "不要去 B 站搜明河", "别搜B站"):
            with self.subTest(q=q):
                self.assertIsNone(search_intent(q).source)
        self.assertIsNone(search_intent("不要联网", True).source)
        route = search_intent("请只在 B 站搜索明河配队")
        self.assertEqual((route.local, route.source, route.subject), (False, "bilibili", "明河配队"))
        self.assertEqual(search_intent("去豆瓣搜游戏资料", True).unsupported, "豆瓣")


class SearchRoutingTests(TestCase):
    def setUp(self):
        self.enterContext(patch("rag.video_retrieval.retrieval_video_catalog", return_value=[]))
        self.retrieve = self.enterContext(patch.object(services, "retrieve_with_status", return_value=([], "insufficient", "无片段")))
        self.search = self.enterContext(patch.object(services, "search_bili_videos", return_value=[]))

    def test_switch_searches_even_after_local_full_answer(self):
        self.retrieve.return_value = ([{"text": "夜明河种族为龙", "meta": {
            "video_id": "BV1FTsE6UEai", "start": 342, "end": 347,
        }}], "insufficient", "相关度低")
        with (
            patch.object(services, "_context_answerability", return_value=coverage("none")),
            patch.object(services, "_generate_answer", return_value="夜明河是龙。[引用1]"),
            patch.object(services, "_review_draft", return_value=coverage("full")),
        ):
            response = TestClient(app).post("/api/ask", json={"question": "明河的种族", "web_search": True})
        self.assertEqual(response.status_code, 200)
        self.search.assert_called_once()
        self.assertIn("夜明河是龙", response.text)
        self.assertIn("event: done", response.text)

    def test_site_only_without_switch_skips_local_retrieval(self):
        response = TestClient(app).post("/api/ask", json={
            "question": "只搜B站的明河配队", "game_state": {"turn": "第4回合"},
        })
        self.assertEqual(response.status_code, 200)
        self.retrieve.assert_not_called()
        self.assertEqual(self.search.call_args.args[0], "明河配队")

    def test_unsupported_explicit_site_never_substitutes_bilibili(self):
        events = list(services.stream_answer("只在知乎搜明河配队", web_search=True))
        self.search.assert_not_called()
        self.retrieve.assert_not_called()
        self.assertIn("知乎", "".join(e["data"].get("text", "") for e in events))

    def test_only_current_message_authorizes_web(self):
        with patch.object(services, "_rewrite_query", return_value="去B站搜明河"):
            list(services.stream_answer("那明河呢", history=[{"role": "user", "content": "去B站搜"}]))
        self.retrieve.assert_called()
        self.search.assert_not_called()

    def test_switch_with_empty_agent_state_still_searches(self):
        with patch("agents.game.agent.update_game_state", return_value=(GameState(), "recommend", True)):
            response = TestClient(app).post("/api/ask", json={
                "question": "帮我找乌萨斯攻略", "game_state": {}, "web_search": True,
            })
        self.assertEqual(response.status_code, 200)
        self.search.assert_called_once()

    def test_web_does_not_mix_in_other_authors(self):
        self.search.return_value = [{"bvid": "BVexample", "author": "其他博主", "title": "攻略"}]
        with (
            patch("rag.video_retrieval.retrieval_video_catalog", return_value=[
                {"eligible": True, "author": "萧然Q", "video_id": "local"},
            ]),
            patch.object(services, "retrieve_external") as subtitles,
        ):
            events = list(services.stream_answer("萧然Q的明河配队是什么", web_search=True))
        subtitles.assert_not_called()
        result = next(e for e in events if e["event"] == "external_search")
        self.assertEqual(result["data"]["videos"], [])
