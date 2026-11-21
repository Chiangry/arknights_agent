"""离线契约/范围隔离测试；PG 集成测试需 RUN_PG_TESTS=1，所有写入回滚。"""
import os
import uuid
from contextlib import contextmanager
from unittest import TestCase, skipUnless
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app import services
from index.catalog import VideoMetadata, RetrievalScope
from index import store


class MetadataContractTests(TestCase):
    def test_unknown_and_mismatched_classification_rejected(self):
        for data in ({'game_id': 'fake'}, {'game_id': 'arknights', 'category_id': 'aic'},
                     {'category_id': 'aic'}, {'title': '   '}, {'extra': 'bad'}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                VideoMetadata.model_validate(data)
        self.assertIsNone(VideoMetadata().game_id)

    def test_scope_allows_category_alone_and_parameterizes_ids(self):
        scope = RetrievalScope(category_id='aic', video_ids=["x' OR 1=1 --"])
        where, params = store.scope_filter(scope)
        self.assertNotIn(scope.video_ids[0], where)
        self.assertEqual(params, ['aic', scope.video_ids])

    def test_catalog_and_invalid_requests(self):
        client = TestClient(app)
        self.assertEqual(len(client.get('/api/catalog').json()['games']), 2)
        self.assertEqual(client.post('/api/ask', json={'question': 'test', 'scope': {'game_id': 'invalid'}}).status_code, 422)
        self.assertEqual(client.post('/api/videos', data={'url': 'BV1U5WS6JEZJ', 'metadata': '{invalid'}).status_code, 422)

    def test_scope_reaches_plain_and_agent_answers(self):
        client = TestClient(app)
        scope = {'game_id': 'endfield', 'category_id': 'aic', 'video_ids': ['test']}
        with patch.object(services, 'stream_answer', return_value=iter([])) as answer:
            client.post('/api/ask', json={'question': '如何建设', 'scope': scope})
            self.assertEqual(answer.call_args.kwargs['scope'].model_dump(), scope)
        def fake_agent(question, previous, *, top_k, task_id, answer):
            yield from answer(question, top_k=top_k, task_id=task_id)
        with patch('app.routers.qa.stream_game_answer', side_effect=fake_agent), patch.object(services, 'stream_answer', return_value=iter([])) as answer:
            client.post('/api/ask', json={'question': '下一步', 'game_state': {}, 'scope': scope})
            self.assertEqual(answer.call_args.kwargs['scope'].model_dump(), scope)

    def test_scope_never_silently_searches_bilibili(self):
        scope = RetrievalScope(video_ids=['only-this'])
        with patch.object(services, 'retrieve_with_status', return_value=([], 'insufficient', '无片段')) as retrieve, \
             patch.object(services, 'search_bili_videos') as external, \
             patch('rag.video_retrieval.retrieval_video_catalog', return_value=[]):
            events = list(services.stream_answer('怎么玩', scope=scope))
        self.assertEqual(retrieve.call_args.kwargs['scope'], scope)
        external.assert_not_called()
        self.assertTrue(any('限定范围' in str(event) for event in events))

    def test_both_search_channels_filter_before_limit(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = []
        @contextmanager
        def fake_conn():
            yield conn
        with patch.object(store, '_conn', fake_conn):
            store.hybrid_search([1.0], '乌萨斯', 5, RetrievalScope(game_id='arknights', video_ids=['v']))
        self.assertEqual(conn.execute.call_count, 2)
        for call in conn.execute.call_args_list:
            query, args = call.args
            self.assertLess(query.index('v.game_id = %s'), query.index('LIMIT'))
            self.assertIn('v.video_id = ANY(%s)', query)
            self.assertIn('arknights', args)
            self.assertIn(['v'], args)


@skipUnless(os.getenv('RUN_PG_TESTS') == '1', '需要本地 PostgreSQL')
class MetadataPostgresTests(TestCase):
    def test_roundtrip_and_search_isolation_without_persisting_fixtures(self):
        import psycopg
        prefix = 'test-metadata-' + uuid.uuid4().hex
        vec = [1.0] + [0.0] * 1023
        with psycopg.connect(store._dsn(), autocommit=True) as connection:
            with connection.transaction(force_rollback=True):
                class Proxy:
                    def __getattr__(self, key):
                        return getattr(connection, key)
                    def commit(self):
                        pass
                @contextmanager
                def test_conn():
                    yield Proxy()
                with patch.object(store, '_conn', test_conn):
                    a, b = prefix + '-a', prefix + '-b'
                    for vid, game, category in [(a, 'arknights', 'main'), (b, 'endfield', 'aic')]:
                        store.save_video_metadata(vid, {'title': '人工标题', 'author': vid,
                                                        'game_id': game, 'category_id': category}, create=True)
                        store.add_chunks(vid, [{'text': '乌萨斯测试', 'start': 12, 'end': 30}], [vec], title='平台标题', source='字幕')
                    self.assertEqual(store.get_video(a)['title'], '人工标题')
                    self.assertEqual(store.get_video(a)['duration'], 30)
                    self.assertEqual(store.get_video(a)['chunk_count'], 1)
                    evidence = {"start":12,"end":20,"text":"画面展示开局顺序","evidence_source":"攻略画面"}
                    self.assertEqual(store.append_evidence_chunks(a, [evidence], [vec], window=(0, 45)), 1)
                    self.assertEqual(store.append_evidence_chunks(a, [evidence], [vec]), 0)
                    store.save_failed_visual_window(a, 45, 90, "timeout")
                    self.assertEqual([w["status"] for w in store.list_visual_windows(a)], ["indexed", "failed"])
                    self.assertEqual(store.append_evidence_chunks(a, [], [], window=(45, 90)), 0)
                    self.assertEqual([w["status"] for w in store.list_visual_windows(a)], ["indexed", "empty"])
                    mixed = store.hybrid_search(vec, "", 10, RetrievalScope(video_ids=[a]))
                    self.assertEqual({h["meta"]["source"] for h in mixed}, {"字幕", "攻略画面"})
                    self.assertEqual(len(store.expand_neighbors(mixed)), 2)
                    first = store.list_video_chunks(a, "", 1, 0)
                    second = store.list_video_chunks(a, "", 1, 1)
                    self.assertEqual(first["total"], 2)
                    self.assertEqual(first["chunks"][0]["source"], "字幕")
                    self.assertEqual(second["chunks"][0]["source"], "攻略画面")
                    match = store.list_video_chunks(a, "开局", 20, 0)
                    self.assertEqual(match["total"], 1)
                    self.assertEqual(match["chunks"][0]["text"], evidence["text"])
                    self.assertEqual(store.list_video_chunks(a, "%", 20, 0), {"total": 0, "chunks": []})
                    store.enrich_video_metadata(a, {'title': '不覆盖', 'cover_url': 'https://example.org/cover.jpg'})
                    self.assertEqual(store.get_video(a)['title'], '人工标题')
                    self.assertEqual(store.get_video(a)['cover_url'], 'https://example.org/cover.jpg')
                    scope = RetrievalScope(game_id='arknights', video_ids=[a, b])
                    self.assertEqual([v['video_id'] for v in store.list_videos(scope)], [a])
                    from rag.video_retrieval import plan_video_retrieval
                    question = f'{a}的乌萨斯'
                    plan = plan_video_retrieval(question, question, scope)
                    self.assertEqual(plan.scope.video_ids, [a])
                    self.assertEqual(plan.query, '乌萨斯')
                    for hits in (store.search(vec, 5, scope), store.hybrid_search(vec, '乌萨斯', 5, scope)):
                        self.assertEqual({h['meta']['video_id'] for h in hits}, {a})
                    store.save_video_metadata(a, {'game_id': 'endfield', 'category_id': 'aic', 'stage_name': '测试区域'})
                    self.assertEqual(store.list_videos(scope), [])
                    self.assertEqual(store.get_video(a)['chunk_count'], 2)
                    store.save_video_metadata(a, {'game_id': None, 'category_id': None})
                    self.assertIsNone(store.get_video(a)['game_id'])
                    self.assertEqual(store.get_video(a)['stage_name'], '测试区域')
                    self.assertTrue(store.delete_video(a))
                    self.assertEqual(store.list_visual_windows(a), [])
                    self.assertFalse(store.delete_video(a))
                    self.assertIsNone(store.get_video(a))
                    self.assertIsNone(store.list_video_chunks(a, "", 20, 0))
                    self.assertFalse(store.video_exists(a))
                    self.assertEqual(store.hybrid_search(vec, '乌萨斯', 5, RetrievalScope(video_ids=[a])), [])
                    self.assertTrue(store.video_exists(b))
