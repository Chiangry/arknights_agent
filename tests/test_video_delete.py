from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import tasks
from app.main import app
from index.store import VideoImportBusy


class VideoDeleteTests(TestCase):
    def test_only_selected_video_is_deleted(self):
        video_id = "local:" + "1" * 64
        with patch("app.routers.videos.delete_video", return_value=True) as delete:
            response = TestClient(app).delete(
                "/api/videos/" + video_id, headers={"Origin": "http://127.0.0.1:5173"},
            )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        delete.assert_called_once_with(video_id)

    def test_unknown_browser_origin_cannot_delete(self):
        with patch("app.routers.videos.delete_video") as delete:
            response = TestClient(app).delete(
                "/api/videos/BV1qc4i6aEGQ", headers={"Origin": "https://unrelated.example"},
            )
        self.assertEqual(response.status_code, 403)
        delete.assert_not_called()

    def test_current_frontend_port_can_delete(self):
        video_id = "local:" + "2" * 64
        for host in ("127.0.0.1", "localhost"):
            with self.subTest(host=host), patch("app.routers.videos.delete_video", return_value=True) as delete:
                response = TestClient(app).delete(
                    "/api/videos/" + video_id, headers={"Origin": f"http://{host}:3000"},
                )
                self.assertEqual(response.status_code, 204)
                delete.assert_called_once_with(video_id)

    def test_queued_visual_supplement_blocks_delete(self):
        task_id = tasks.create_task("bili-visual", "BV1qc4i6aEGQ:0:45")
        self.addCleanup(tasks.finish_ephemeral, task_id)
        with patch("app.routers.videos.delete_video") as delete:
            response = TestClient(app).delete("/api/videos/BV1qc4i6aEGQ")
        self.assertEqual(response.status_code, 409)
        delete.assert_not_called()

    def test_in_progress_lock_returns_conflict(self):
        with patch("app.routers.videos.delete_video", side_effect=VideoImportBusy):
            self.assertEqual(TestClient(app).delete("/api/videos/BV1qc4i6aEGQ").status_code, 409)

    def test_missing_video_returns_not_found(self):
        with patch("app.routers.videos.delete_video", return_value=False):
            self.assertEqual(TestClient(app).delete("/api/videos/BV1qc4i6aEGQ").status_code, 404)
