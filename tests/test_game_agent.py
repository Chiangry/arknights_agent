"""对局 Agent 和普通问答共享证据流的离线回归测试。"""

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from agents.game import GameState, stream_game_answer
from agents.game.state import Action
from app import services, tasks
from app.main import app


def model_result(content):
    choice = SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))
    return SimpleNamespace(choices=[choice])


def completion_client(*outputs):
    client = Mock()
    client.chat.completions.create.side_effect = [model_result(output) for output in outputs]
    return client


def read_events(response):
    response.raise_for_status()
    return [
        {"event": lines[0].removeprefix("event: "), "data": json.loads(lines[1].removeprefix("data: "))}
        for block in response.text.strip().split("\n\n")
        if (lines := block.splitlines()) and lines[0].startswith("event: ")
    ]


class GameAgentTests(TestCase):
    def test_plain_question_does_not_enter_game_agent(self):
        with (
            patch("app.routers.qa.stream_game_answer") as game,
            patch.object(services, "retrieve_with_status", return_value=([], "insufficient", "无片段")) as retrieve,
            patch.object(services, "search_bili_videos", return_value=[]) as search,
        ):
            events = read_events(TestClient(app).post("/api/ask", json={"question": "乌萨斯怎么玩"}))

        game.assert_not_called()
        retrieve.assert_called_once_with("乌萨斯怎么玩", None)
        search.assert_called_once()
        self.assertEqual(events[-1]["event"], "done")
        self.assertIsNone(tasks.get_task(events[0]["data"]["task_id"]))

    def test_reset_returns_state_without_retrieval(self):
        with patch.object(services, "retrieve_with_status") as retrieve:
            events = read_events(TestClient(app).post("/api/ask", json={
                "question": "换一局",
                "game_state": {"turn": "第4回合"},
            }))

        retrieve.assert_not_called()
        self.assertEqual(next(item["data"]["turn"] for item in events if item["event"] == "game_state"), None)
        self.assertIn("已清空上一局", next(item["data"]["text"] for item in events if item["event"] == "delta"))
        self.assertEqual(events[-1]["event"], "done")

    def test_all_blocked_options_are_explained_without_retrieval(self):
        previous = GameState(resources={"金币": 3}, options=[Action(name="升级", costs={"金币": 5})])
        answer = Mock()
        with patch("agents.game.state.get_client", return_value=completion_client(
            '{"intent":"recommend","patch":{}}',
        )):
            events = list(stream_game_answer("下一步怎么选", previous, top_k=5, task_id="test", answer=answer))

        answer.assert_not_called()
        self.assertIn("金币需 5，现有 3", next(item["data"]["text"] for item in events if item["event"] == "delta"))
        self.assertEqual(events[-1]["event"], "done")

    def test_partial_game_answer_falls_back_and_keeps_confirmation_gate(self):
        previous = GameState(
            faction="乌萨斯", turn="第4回合", resources={"金币": 3},
            options=[Action(name="刷新", costs={"金币": 2})],
        )
        hit = {"text": "刷新商店消耗两金币", "meta": {"video_id": "BVlocal", "start": 3, "end": 7}}
        client = completion_client(
            "本局可以刷新商店，但缺少阵容调整的依据。[引用1]",
            '{"verdict":"partial","reason":"缺少阵容依据","missing":["阵容选择"]}',
        )
        task_id = tasks.create_task("ask", "")
        tasks.update_task(task_id, status="processing")
        self.addCleanup(tasks.finish_ephemeral, task_id)

        with (
            patch("agents.game.state.get_client", return_value=completion_client(
                '{"intent":"recommend","patch":{}}',
            )),
            patch.object(services, "get_client", return_value=client),
            patch.object(services, "retrieve_with_status", return_value=([hit], "insufficient", "证据不足")) as retrieve,
            patch.object(services, "search_bili_videos", return_value=[{"bvid": "BVexample", "title": "攻略"}]) as search,
            patch.object(services, "retrieve_external", return_value=([], 0)),
            patch.object(services, "get_cached_bili_transcript", return_value=None),
            patch.object(services, "video_exists", return_value=False),
            patch.object(services, "_rank_audio", return_value=[]),
            patch.object(services, "_transcribe_candidate") as transcribe,
        ):
            stream = stream_game_answer("下一步怎么选", previous, top_k=5, task_id=task_id, answer=services.stream_answer)
            events = []
            for item in stream:
                events.append(item)
                if item["event"] == "audio_confirmation":
                    transcribe.assert_not_called()
                    self.assertTrue(tasks.decide_audio_confirmation(task_id, False))

        retrieve.assert_called_once_with("乌萨斯 第4回合 刷新 下一步怎么选", 5)
        self.assertIn("阵容选择", search.call_args.args[0])
        generate, review = client.chat.completions.create.call_args_list
        self.assertIn("待确认动作只能作条件建议", generate.kwargs["messages"][0]["content"])
        review_input = json.loads(review.kwargs["messages"][1]["content"])
        self.assertEqual(review_input["question"], "下一步怎么选")
        self.assertEqual(review_input["当前对局与行动约束"]["可以执行"], ["刷新"])
        event_names = [item["event"] for item in events]
        self.assertLess(event_names.index("delta"), event_names.index("external_search"))
        self.assertIn("audio_confirmation", event_names)
        transcribe.assert_not_called()
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["data"]["citations"][0]["start"], 3)
