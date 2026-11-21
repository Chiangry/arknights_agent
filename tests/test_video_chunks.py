from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class VideoChunksTests(TestCase):
    def test_scoped_keyword_and_page(self):
        video_id = "local:" + "1" * 64
        result = {"total": 1, "chunks": [{"id": "1", "chunk_idx": 0, "text": "正文",
                  "start_sec": 2, "end_sec": 4, "source": "画面"}]}
        with patch("app.routers.videos.list_video_chunks", return_value=result) as read:
            response = TestClient(app).get(f"/api/videos/{video_id}/chunks", params={
                "query": " 正文 ", "limit": 5, "offset": 0,
            })
        self.assertEqual(response.json(), result)
        read.assert_called_once_with(video_id, "正文", 5, 0)

    def test_missing_and_empty_are_distinct(self):
        with patch("app.routers.videos.list_video_chunks", side_effect=[None, {"total": 0, "chunks": []}]):
            client = TestClient(app)
            self.assertEqual(client.get("/api/videos/missing/chunks").status_code, 404)
            empty = client.get("/api/videos/draft/chunks")
            self.assertEqual(empty.status_code, 200)
            self.assertEqual(empty.json(), {"total": 0, "chunks": []})

    def test_bounds_page_size(self):
        with patch("app.routers.videos.list_video_chunks") as read:
            self.assertEqual(TestClient(app).get("/api/videos/a/chunks?limit=101").status_code, 422)
            read.assert_not_called()
