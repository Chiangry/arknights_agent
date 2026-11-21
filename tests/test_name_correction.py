from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import Mock, patch

from app import services, tasks
from ingest.name_correction import VISUAL_CAPTION, VISUAL_CARD, WHISPER_LOCAL, VideoNameCorrection


TITLE = "雷公？畏兽？夜明河的原型究竟是什么？"
CAPTION = {"text": "底部硬字幕：聊了夜明河可能的神话原型", "evidence_source": VISUAL_CAPTION,
           "start": 14.4, "end": 16.8}
SPEECH = {"text": "那就是叶铭河的种族 叶铭河种族为龙 而他耳朵的特征",
          "evidence_source": WHISPER_LOCAL, "start": 315, "end": 359.93}


class NameCorrectionTests(TestCase):
    def test_real_case_preserves_conclusion_timestamps_and_original(self):
        corrector = VideoNameCorrection(TITLE)
        corrector.observe_chunks([CAPTION])
        self.assertEqual(corrector.correct([SPEECH]), [{
            **SPEECH, "text": "那就是夜明河的种族 夜明河种族为龙 而他耳朵的特征",
            "original_text": SPEECH["text"],
        }])

    def test_title_alone_or_card_inference_is_not_enough(self):
        corrector = VideoNameCorrection(TITLE)
        corrector.observe_chunks([dict(CAPTION, evidence_source=VISUAL_CARD, text="画面模糊\n模型解读：夜明河")])
        self.assertEqual(corrector.correct([SPEECH]), [SPEECH])

    def test_homophonic_names_or_conflicting_caption_are_not_rewritten(self):
        corrector = VideoNameCorrection(TITLE + "？叶铭河的技能")
        corrector.observe_chunks([CAPTION])
        self.assertEqual(corrector.correct([SPEECH]), [SPEECH])
        corrector = VideoNameCorrection(TITLE)
        corrector.observe_chunks([CAPTION, dict(CAPTION, text="叶铭河也是一名角色")])
        self.assertEqual(corrector.correct([SPEECH]), [SPEECH])

    def test_does_not_rewrite_caption_or_unrelated_mention(self):
        corrector = VideoNameCorrection(TITLE)
        corrector.observe_chunks([CAPTION])
        caption = dict(SPEECH, evidence_source=VISUAL_CAPTION)
        unrelated = dict(SPEECH, text="叶铭河说这次不错")
        self.assertEqual(corrector.correct([caption, unrelated]), [caption, unrelated])

    def test_whole_video_uses_previous_window_before_embedding(self):
        speech = dict(SPEECH, start=45, end=84)
        with (
            patch.object(services, "list_visual_windows", return_value=[]),
            patch.object(services, "list_chunk_references", return_value=[]),
            patch.object(services, "qwen_config"),
            patch.object(tasks, "wait_visual_confirmation", return_value="approved"),
            patch.object(services, "get_visual_or_audio_chunks", side_effect=[[CAPTION], [speech]]),
            patch.object(services, "embed_texts", return_value=[[1.0]]) as embed,
            patch.object(services, "lock_video_ingest", return_value=nullcontext()),
            patch.object(services, "append_evidence_chunks", return_value=1) as store,
        ):
            count, report = services._process_whole_video("task", "BV1FTsE6UEai", 90, Mock(), title=TITLE)
        self.assertEqual((count, report["with_evidence"]), (2, 2))
        self.assertIn("夜明河种族为龙", embed.call_args.args[0][0])
        stored = store.call_args.args[1][0]
        self.assertEqual(stored["text"], embed.call_args.args[0][0])
        self.assertEqual(stored["original_text"], SPEECH["text"])
