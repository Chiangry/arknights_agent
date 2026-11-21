from contextlib import nullcontext
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app import services, tasks
from app.main import app
from ingest import visual_ingest
from ingest.visual_ingest import VisualRange, visual_chunks


REPORT = {"facts": [{
    "kind": "rotation", "source": "visual", "start_sec": 1, "end_sec": 4,
    "claim": "操作顺序", "evidence": "充能轴 1EE1EE",
}, {
    "kind": "subtitle", "source": "visual", "start_sec": 4, "end_sec": 6,
    "claim": "不要凭这句推断", "evidence": "仅保留画面文字",
}], "uncertain": []}


class VisualIngestTests(TestCase):
    def test_bili_import_defaults_to_auto(self):
        with (patch("app.routers.videos.reserve_with_metadata", return_value=("test", True)),
              patch.object(services, "run_visual_ingest") as run):
            response = TestClient(app).post("/api/videos", data={"url": "BV1qc4i6aEGQ"})
        self.assertEqual(response.status_code, 200)
        run.assert_called_once_with("test", "BV1qc4i6aEGQ", None)

    def test_visual_consent_available_only_for_recommended_window(self):
        task_id = tasks.create_task("bili-auto", "BV1qc4i6aEGQ")
        self.addCleanup(tasks.finish_ephemeral, task_id)
        tasks.update_task(task_id, status="processing")
        client = TestClient(app)
        uri = f"/api/tasks/{task_id}/visual-confirmation"
        self.assertEqual(client.post(uri, json={"approved": True}).status_code, 409)
        decisions = []
        thread = Thread(target=lambda: decisions.append(tasks.wait_visual_confirmation(task_id, 0, 45, "发现可见文字", timeout=5)))
        thread.start()
        try:
            until = monotonic() + 2
            while not (details := tasks.snapshot(task_id)["data"]["visual_confirmation"]) and monotonic() < until:
                sleep(0.01)
            self.assertEqual((details["start"], details["seconds"]), (0, 45))
            self.assertEqual(client.post(uri, json={"approved": True},
                                         headers={"Origin": "https://unrelated.example"}).status_code, 403)
            self.assertEqual(client.post(uri, json={"approved": False}).status_code, 204)
        finally:
            thread.join(timeout=5)
        self.assertEqual(decisions, ["declined"])
        self.assertEqual(client.post(uri, json={"approved": True}).status_code, 409)

    def test_visual_consent_times_out_without_upload(self):
        task_id = tasks.create_task("bili-auto", "BV1qc4i6aEGQ")
        self.addCleanup(tasks.finish_ephemeral, task_id)
        tasks.update_task(task_id, status="processing")
        self.assertEqual(tasks.wait_visual_confirmation(task_id, 0, 45, "样本", timeout=0), "expired")
        self.assertIsNone(tasks.snapshot(task_id)["data"]["visual_confirmation"])
        self.assertFalse(tasks.decide_visual_confirmation(task_id, True))

    def test_auto_samples_before_consent_and_decline_never_uploads_or_transcribes(self):
        with (
            patch.object(visual_ingest, "qwen_config", return_value=("key", "url")),
            patch.object(visual_ingest, "download_clip", return_value=Path("sample.mp4")) as download,
            patch.object(visual_ingest, "check_clip", return_value=45),
            patch.object(visual_ingest, "scan_text", side_effect=[False, True]),
            patch.object(visual_ingest, "make_visual_clip") as prepare,
            patch.object(visual_ingest, "extract_qwen") as upload,
            patch.object(visual_ingest, "transcribe") as whisper,
        ):
            confirm = Mock(return_value="declined")
            with self.assertRaisesRegex(ValueError, "已跳过上传"):
                visual_ingest.get_visual_or_audio_chunks("BV1qc4i6aEGQ", None, Mock(), duration=200, confirm=confirm)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(confirm.call_args.args[0], VisualRange(90, 45))
        prepare.assert_not_called()
        upload.assert_not_called()
        whisper.assert_not_called()

    def test_auto_approved_upload_uses_recommended_window_and_keeps_video_times(self):
        order = []
        def confirm(sample, reason):
            order.append("approved")
            self.assertEqual(sample, VisualRange(90, 45))
            return "approved"

        def extract(clip, duration, key, endpoint, *, visual_only, task_id):
            order.append("uploaded")
            self.assertTrue(visual_only)
            self.assertEqual(clip.name, "visual.mp4")
            return REPORT

        with (
            patch.object(visual_ingest, "qwen_config", return_value=("key", "url")),
            patch.object(visual_ingest, "download_clip", return_value=Path("sample.mp4")),
            patch.object(visual_ingest, "check_clip", return_value=45),
            patch.object(visual_ingest, "scan_text", side_effect=[False, True]),
            patch.object(visual_ingest, "make_visual_clip"),
            patch.object(visual_ingest, "extract_qwen", side_effect=extract),
        ):
            chunks = visual_ingest.get_visual_or_audio_chunks("BV1qc4i6aEGQ", None, Mock(), duration=200, confirm=confirm)
        self.assertEqual(order, ["approved", "uploaded"])
        self.assertEqual((chunks[0]["start"], chunks[0]["end"]), (91, 94))

    def test_video_submit_requires_upload_consent(self):
        with patch("app.routers.videos.reserve_with_metadata") as reserve:
            result = TestClient(app).post("/api/videos", data={
                "url": "BV1qc4i6aEGQ", "visual_start": "0", "visual_seconds": "45",
            })
        self.assertEqual(result.status_code, 422)
        reserve.assert_not_called()

    def test_captions_and_visual_interpretation_keep_distinct_sources(self):
        visual, caption = visual_chunks(REPORT, 60)
        self.assertEqual((visual["start"], visual["end"]), (61, 64))
        self.assertIn("攻略画面", visual["evidence_source"])
        self.assertIn("硬字幕", caption["evidence_source"])
        self.assertEqual(caption["text"], "仅保留画面文字")

    def test_visual_evidence_skips_whisper(self):
        with (
            patch.object(visual_ingest, "qwen_config", return_value=("key", "url")),
            patch.object(visual_ingest, "download_clip", return_value=Path("sample.mp4")),
            patch.object(visual_ingest, "check_clip", return_value=45),
            patch.object(visual_ingest, "scan_text", return_value=True),
            patch.object(visual_ingest, "make_visual_clip"),
            patch.object(visual_ingest, "extract_qwen", return_value=REPORT),
            patch.object(visual_ingest, "transcribe") as whisper,
        ):
            chunks = visual_ingest.get_visual_or_audio_chunks("BV1qc4i6aEGQ", VisualRange(0, 45), Mock())
        self.assertEqual(len(chunks), 2)
        whisper.assert_not_called()

    def test_api_subtitles_indexed_independently_of_whole_video_pass(self):
        with (
            patch.object(services, "lock_video_ingest", return_value=nullcontext()),
            patch.object(services, "get_video", return_value={"duration_seconds": 317}),
            patch.object(services, "fetch_subtitles", return_value=([(1, 3, "字幕")], "CC字幕", "标题", "作者")),
            patch.object(services, "fetch_video_metadata", return_value={}),
            patch.object(services, "enrich_video_metadata"),
            patch.object(services, "has_chunk_source", return_value=False),
            patch.object(services, "_store_whole_video_chunks", return_value=1) as index,
            patch.object(services, "_process_whole_video", return_value=(None, {})) as visual,
        ):
            services.run_visual_ingest("test", "BV1qc4i6aEGQ")
        index.assert_called_once_with("BV1qc4i6aEGQ", [{"start": 1, "end": 3, "text": "字幕", "evidence_source": "CC字幕"}])
        self.assertEqual(visual.call_args.args[2], 317)
        self.assertEqual(visual.call_args.kwargs["subtitles"], [(1, 3, "字幕")])

    def test_full_plan_spans_last_second_without_gaps(self):
        windows = visual_ingest.full_video_ranges(317)
        self.assertEqual(windows[0].start, 0)
        self.assertEqual(windows[-1], VisualRange(270, 47))
        self.assertTrue(all(a.start + a.seconds == b.start for a, b in zip(windows, windows[1:])))

    def test_one_approval_and_failure_does_not_block_later_windows(self):
        ingest = Mock(side_effect=[visual_chunks(REPORT, 0), ValueError("百炼连接失败 abc"),
                                   visual_ingest.NoUsableEvidence(), visual_chunks(REPORT, 135)])
        with (
            patch.object(services, "list_visual_windows", return_value=[]),
            patch.object(services, "qwen_config"),
            patch.object(tasks, "wait_visual_confirmation", return_value="approved") as confirm,
            patch.object(services, "get_visual_or_audio_chunks", ingest),
            patch.object(services, "save_failed_visual_window") as failed,
            patch.object(services, "_store_whole_video_chunks", side_effect=lambda v, c, *, window: len(c)) as store,
        ):
            n, coverage = services._process_whole_video("task", "BV1qc4i6aEGQ", 170, Mock())
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.kwargs["segment_count"], 4)
        self.assertEqual([call.args[1].start for call in ingest.call_args_list], [0, 45, 90, 135])
        self.assertEqual(store.call_args.kwargs["window"], (135, 170))
        self.assertEqual((n, coverage["with_evidence"], coverage["empty"]), (4, 2, 1))
        failed.assert_called_once_with("BV1qc4i6aEGQ", 45, 90, "百炼连接失败 abc")

    def test_no_upload_without_approval_and_resume_only_failed(self):
        rows = [{"start": 0, "end": 45, "status": "indexed", "reason": None},
                {"start": 45, "end": 90, "status": "failed", "reason": "timeout"},
                {"start": 90, "end": 135, "status": "empty", "reason": None}]
        with (
            patch.object(services, "list_visual_windows", return_value=rows),
            patch.object(services, "qwen_config"),
            patch.object(tasks, "wait_visual_confirmation", side_effect=["declined", "approved"]) as confirm,
            patch.object(services, "get_visual_or_audio_chunks", return_value=[]) as ingest,
            patch.object(services, "_store_whole_video_chunks", return_value=0),
        ):
            denied, _ = services._process_whole_video("first", "BV1qc4i6aEGQ", 135, Mock())
            ingest.assert_not_called()
            _, coverage = services._process_whole_video("retry", "BV1qc4i6aEGQ", 135, Mock())
        self.assertIsNone(denied)
        self.assertEqual(confirm.call_args.kwargs["segment_count"], 1)
        self.assertEqual(ingest.call_args.args[1], VisualRange(45, 45))
        self.assertEqual(coverage["failed"], [])

    def test_empty_visual_result_transcribes_only_selected_window(self):
        with (
            patch.object(visual_ingest, "qwen_config", return_value=("key", "url")),
            patch.object(visual_ingest, "download_clip", return_value=Path("sample.mp4")),
            patch.object(visual_ingest, "check_clip", return_value=45),
            patch.object(visual_ingest, "scan_text", return_value=False),
            patch.object(visual_ingest, "make_visual_clip"),
            patch.object(visual_ingest, "extract_qwen", return_value={"facts": [], "uncertain": []}),
            patch.object(visual_ingest.subprocess, "run") as ffmpeg,
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "stat") as stat,
            patch.object(visual_ingest, "decode_audio"),
            patch.object(visual_ingest, "get_speech_timestamps", return_value=[{"start": 0, "end": 32000}]),
            patch.object(visual_ingest, "transcribe", return_value=[(1, 5, "明河的实际推荐配队和操作顺序")]) as whisper,
        ):
            stat.return_value.st_size = 100
            chunks = visual_ingest.get_visual_or_audio_chunks("BV1qc4i6aEGQ", VisualRange(100, 45), Mock())
        self.assertEqual((chunks[0]["start"], chunks[0]["end"]), (101, 105))
        self.assertIn("局部转写", chunks[0]["evidence_source"])
        self.assertTrue(whisper.call_args.args[0].endswith("selected.wav"))
        self.assertIn("sample.mp4", ffmpeg.call_args.args[0])

    def test_existing_video_appends_without_replacing(self):
        chunks = visual_chunks(REPORT, 0)
        with (
            patch.object(services, "lock_video_ingest", return_value=nullcontext()),
            patch.object(services, "video_exists", return_value=True),
            patch.object(services, "get_visual_or_audio_chunks", return_value=chunks),
            patch.object(services, "_embed_chunks", return_value=[[1], [2]]),
            patch.object(services, "append_evidence_chunks", return_value=2) as append,
            patch.object(services, "add_chunks") as replace,
        ):
            services.run_visual_ingest("test", "BV1qc4i6aEGQ", VisualRange(0, 45))
        append.assert_called_once_with("BV1qc4i6aEGQ", chunks, [[1], [2]])
        replace.assert_not_called()
