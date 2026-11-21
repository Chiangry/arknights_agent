from unittest import TestCase
from unittest.mock import Mock, patch

from index.tokenizer import query_terms, tokenize
from ingest.chunker import build_chunks, build_semantic_chunks
from ingest.transcribe import transcribe
from ingest.visual_ingest import visual_chunks
from rag import retriever
from scripts.migrate_simplified_chunks import migrate
from text_normalization import to_simplified


class SimplifiedTextTests(TestCase):
    def test_normalization_does_not_guess_names(self):
        self.assertEqual(to_simplified("葉銘河種族為龍，FPS 60"), "叶铭河种族为龙，FPS 60")
        self.assertEqual(to_simplified("夜明河种族为龙"), "夜明河种族为龙")

    def test_transcription_and_chunking_preserve_times(self):
        model = Mock()
        model.transcribe.return_value = ([Mock(start=1.0, end=3.0, text=" 種族為龍 ")], Mock(duration=3.0))
        with patch("ingest.transcribe.get_model", return_value=model), patch("config.WHISPER_BATCH_SIZE", 0):
            self.assertEqual(transcribe("sample.wav"), [(1.0, 3.0, "种族为龙")])
        for chunker in (build_chunks, build_semantic_chunks):
            self.assertEqual(chunker([(1.0, 3.0, "種族為龍")]),
                             [{"start": 1.0, "end": 3.0, "text": "种族为龙"}])

    def test_visual_evidence_and_interpretation_are_both_normalized(self):
        chunks = visual_chunks({"facts": [
            {"kind": "subtitle", "evidence": "畫面顯示「龍」", "claim": "", "start_sec": 1, "end_sec": 2},
            {"kind": "visual_text", "evidence": "種族：龍", "claim": "資料卡", "start_sec": 2, "end_sec": 3},
        ]}, 45)
        self.assertEqual(chunks[0]["text"], "画面显示「龙」")
        self.assertEqual((chunks[0]["start"], chunks[1]["end"]), (46, 48))
        self.assertEqual(chunks[1]["text"], "画面原文或线索：种族：龙\n模型解读：资料卡")

    def test_query_normalized_before_vector_and_full_text_search(self):
        q = "明河的種族是什麼"
        self.assertEqual(query_terms(q), "明河 种族")
        with (
            patch.object(retriever, "embed_texts", return_value=[[1.0]]) as embed,
            patch.object(retriever, "hybrid_search", return_value=[]) as search,
            patch.object(retriever, "attribute_search", return_value=[]),
        ):
            retriever.retrieve(q)
        embed.assert_called_once_with(["明河的种族是什么 夜明河"])
        self.assertEqual(search.call_args.args[1], "明河 种族")

    def test_migration_preview_is_read_only_and_apply_rebuilds_tokens(self):
        conn = Mock()
        conn.execute.return_value.fetchall.side_effect = [[(60, "種族為龍", "種族")], []]
        self.assertEqual(migrate(conn, video_id="BV1FTsE6UEai"), (1, 1, 0))
        conn.cursor.assert_not_called()
        conn.execute.return_value.fetchall.side_effect = [[(60, "種族為龍", "種族")], []]
        cursor = conn.cursor.return_value.__enter__ = Mock()
        cursor.return_value.rowcount = 1
        conn.cursor.return_value.__exit__ = Mock()
        self.assertEqual(migrate(conn, apply=True), (1, 1, 1))
        sql, values = cursor.return_value.executemany.call_args.args
        self.assertEqual(values, [("种族为龙", tokenize("种族为龙"), 60, "種族為龍", "種族")])
        self.assertNotIn("embedding", sql)
