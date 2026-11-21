import copy
from contextlib import contextmanager
import os
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg import sql

from app import chat_store, chat_turns, services
from app.main import app
from index.store import _conn
from rag.answer_events import publish_answer, step


class TurnCheckpointTests(TestCase):
    def test_checkpoint_preserves_partial_and_marks_failure(self):
        saved = []
        emitted = []

        def generate():
            yield step("knowledge_search", "completed", "找到了资料")
            yield {"event": "delta", "data": {"text": "已经生成的内容"}}
            raise RuntimeError("planned")

        def checkpoint(_thread, _message, snapshot, _state):
            saved.append(copy.deepcopy(snapshot))
            return True

        with patch.object(chat_store, "checkpoint", side_effect=checkpoint), self.assertLogs("app.chat_turns"):
            chat_turns._run("test", 1, generate, lambda event, _data: emitted.append(event))
        self.assertEqual([s["status"] for s in saved], ["running", "running", "failed"])
        self.assertEqual(saved[-1]["content"], "已经生成的内容")
        self.assertEqual(saved[-1]["steps"][0]["stage"], "knowledge_search")
        self.assertEqual(emitted, ["agent_step", "delta", "error"])


@skipUnless(os.getenv("RUN_CHAT_PG_TESTS") == "1", "需要本地 PostgreSQL，仅在显式启用时执行")
class ChatPostgresTests(TestCase):
    def setUp(self):
        self.schema = sql.Identifier("chat_test_" + uuid4().hex)
        with _conn() as c:
            c.execute(sql.SQL("CREATE SCHEMA {}").format(self.schema))
        self.addCleanup(self.drop_schema)

        @contextmanager
        def scoped_conn():
            with _conn() as c:
                c.execute(sql.SQL("SET LOCAL search_path TO {},public").format(self.schema))
                yield c

        self.enterContext(patch.object(chat_store, "_conn", scoped_conn))
        with scoped_conn() as c:
            c.execute(Path("deploy/migrations/005_chat_history.sql").read_text())
        self.client = TestClient(app)
        self.base = "/api/chat/threads"

    def drop_schema(self):
        with _conn() as c:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(self.schema))

    def create(self, **fields):
        thread_id = str(uuid4())
        response = self.client.post(self.base, json={"id": thread_id, **fields})
        self.assertEqual(response.status_code, 201, response.text)
        return thread_id

    def test_persists_turn_replay_and_sort_order(self):
        one, two = self.create(), self.create(title="另一个会话")
        path = f"{self.base}/{one}"
        cite = {"video_id": "BV1FTsE6UEai", "start": 342, "end": 347, "text": "无需复制的正文"}

        def generate(q, _top_k, history, _task, scope=None):
            self.assertEqual(scope.video_ids, ["BV1FTsE6UEai"])
            if q == "追问":
                self.assertEqual(history, [{"role": "user", "content": "明河的种族"},
                                           {"role": "assistant", "content": "是龙。[引用1]"}])
            yield step("knowledge_search", "completed", "命中")
            yield from publish_answer("是龙。[引用1]", [cite])

        self.assertEqual(self.client.patch(path, json={"scope": {"video_ids": ["BV1FTsE6UEai"]}}).status_code, 200)
        body = {"question": "明河的种族", "thread_id": one, "request_id": str(uuid4())}
        with patch.object(services, "stream_answer", side_effect=generate) as answer:
            self.assertIn("event: done", self.client.post("/api/ask", json=body).text)
            self.assertIn("event: done", self.client.post("/api/ask", json=body).text)
            self.assertEqual(answer.call_count, 1)
            messages = self.client.get(path).json()["messages"]
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[1]["citations"][0]["start"], 342)
            self.assertNotIn("text", messages[1]["citations"][0])
            self.assertEqual(messages[1]["steps"][0]["stage"], "knowledge_search")
            self.assertIn("event: done", self.client.post("/api/ask", json={
                **body, "question": "追问", "request_id": str(uuid4()),
            }).text)
        self.client.get(f"{self.base}/{two}")
        self.client.patch(f"{self.base}/{two}", json={"title": "已重命名"})
        self.assertEqual([t["id"] for t in self.client.get(self.base).json()], [one, two])
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_restart_recovery_retains_partial_and_state(self):
        thread_id = self.create()
        current = chat_store.begin_turn(thread_id, uuid4(), "怎么打")
        chat_store.checkpoint(thread_id, current["assistant_id"], {
            "content": "这是已保存的部分", "status": "running", "citations": [], "steps": [],
        }, {"turn": "第4回合"})
        with TestClient(app) as restarted:
            thread = restarted.get(f"{self.base}/{thread_id}").json()
        self.assertEqual(thread["messages"][1]["status"], "interrupted")
        self.assertEqual(thread["messages"][1]["content"], "这是已保存的部分")
        self.assertEqual(thread["game_state"]["turn"], "第4回合")
