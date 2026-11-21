from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from index.catalog import suggest_video_category


class VideoPreviewMetadataTests(TestCase):
    def test_preview_is_read_only_and_suggests_category(self):
        with (patch("app.routers.videos.fetch_video_metadata", return_value={
            "title": "【明日方舟：终末地】明河配队、轮椅轴和装备养成",
            "author": "测试作者", "duration_seconds": 317,
        }) as fetch, patch("app.routers.videos.reserve_with_metadata") as reserve,
              patch("app.routers.videos.save_video_metadata") as save):
            response = TestClient(app).get("/api/video-metadata", params={
                "url": "https://www.bilibili.com/video/BV1qc4i6aEGQ/",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestion"], {"game_id": "endfield", "category_id": "combo"})
        self.assertEqual(response.json()["bvid"], "BV1qc4i6aEGQ")
        self.assertEqual(response.json()["duration_seconds"], 317)
        fetch.assert_called_once_with("BV1qc4i6aEGQ")
        reserve.assert_not_called()
        save.assert_not_called()

    def test_ambiguous_title_does_not_default_to_arknights(self):
        self.assertEqual(suggest_video_category("周末实录", ""), {"game_id": None, "category_id": None})

    def test_title_beats_description_cross_game_links(self):
        self.assertEqual(suggest_video_category("明日方舟集成战略攻略", "更多终末地配队"),
                         {"game_id": "arknights", "category_id": "roguelike"})
