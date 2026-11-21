import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ingest import video_understanding as video


class VideoClipTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.clip = Path(folder) / "sample.mp4"
        self.clip.write_bytes(b"ffprobe is mocked")
        self.probe = self.enterContext(patch.object(video.subprocess, "run"))

    def set_duration(self, track, container, *, audio=True):
        streams = [{"codec_type": "video", "duration": track}]
        if audio:
            streams.append({"codec_type": "audio"})
        self.probe.return_value.stdout = json.dumps({
            "streams": streams,
            "format": {"duration": container},
        })

    def test_container_preroll_does_not_reject_valid_clip(self):
        self.set_duration("43.202", "46.834")
        self.assertAlmostEqual(video.check_clip(self.clip, 44), 43.202)

    def test_matching_container_does_not_hide_truncated_video(self):
        self.set_duration("40", "44")
        with self.assertRaisesRegex(ValueError, r"40\.0s.*44\.0s"):
            video.check_clip(self.clip, 44)

    def test_missing_track_duration_uses_container(self):
        self.set_duration("N/A", "44")
        self.assertEqual(video.check_clip(self.clip, 44), 44)

    def test_video_only_is_supported_for_visual_ingest(self):
        self.set_duration("44", "44", audio=False)
        self.assertEqual(video.check_clip(self.clip, 44, require_audio=False), 44)
        with self.assertRaisesRegex(ValueError, "缺少"):
            video.check_clip(self.clip, 44)

    def test_download_reencodes_instead_of_copying_at_keyframes(self):
        with (
            patch.object(video, "ffmpeg_h264_encoder", return_value="h264_videotoolbox"),
            patch.object(video.yt_dlp, "YoutubeDL") as ydl,
        ):
            video.download_clip("BV1FTsE6UEai", 540, 584, self.clip.parent)
        options = ydl.call_args.args[0]
        self.assertTrue(options["force_keyframes_at_cuts"])
        args = options["external_downloader_args"]["ffmpeg_o"]
        self.assertEqual(args[args.index("-c:v") + 1], "h264_videotoolbox")
        self.assertEqual(args[args.index("-fs") + 1], str(video.MAX_CLIP_BYTES))
