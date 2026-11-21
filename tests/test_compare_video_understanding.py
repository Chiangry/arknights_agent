import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import httpx

from scripts.compare_video_understanding import extract_gemini, extract_qwen, qwen_endpoint


class VideoUnderstandingTest(TestCase):
    def response(self, post, *, source="visual", end=4):
        report = {"facts": [{"kind": "lineup", "claim": "画面展示阵容", "source": source,
                             "start_sec": 1, "end_sec": end, "evidence": "角色名可见"}], "uncertain": []}
        reply = post.return_value
        reply.ok = True
        reply.is_redirect = False
        reply.json.return_value = {"candidates": [{"finishReason": "STOP",
            "content": {"parts": [{"text": json.dumps(report)}]}}]}

    @patch("requests.post")
    @patch.object(Path, "read_bytes", return_value=b"fixture")
    def test_sends_video_without_search(self, _, post):
        self.response(post)
        parsed = extract_gemini(Path("sample.mp4"), 45, "fake", "gemini-3.8-flash")
        self.assertEqual(parsed["facts"][0]["source"], "visual")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["contents"][0]["parts"][0]["inlineData"]["mimeType"], "video/mp4")
        self.assertNotIn("tools", payload)
        self.assertNotIn("fake", post.call_args.args[0])

    @patch("requests.post")
    @patch.object(Path, "read_bytes", return_value=b"fixture")
    def test_rejects_out_of_range_evidence(self, _, post):
        self.response(post, end=60)
        with self.assertRaisesRegex(ValueError, "时间点"):
            extract_gemini(Path("sample.mp4"), 45, "fake", "gemini-3.8-flash")

    @patch("httpx.stream")
    @patch.object(Path, "stat")
    @patch.object(Path, "read_bytes", return_value=b"fixture")
    def test_qwen_stream_uses_video_without_search(self, _, stat, post):
        stat.return_value.st_size = 7
        reply = post.return_value.__enter__.return_value
        reply.is_success = True
        reply.status_code = 200
        reply.iter_lines.return_value = [
            "data: " + json.dumps({"choices": [{"delta": {"content": '{"facts":[],'}}]}),
            "data: " + json.dumps({"choices": [{"delta": {"content": '"uncertain":[]}'},
                                               "finish_reason": "stop"}]}),
            'data: [DONE]',
        ]
        url = qwen_endpoint("ws-test", "cn-beijing")
        with self.assertLogs("uvicorn.error.qwen", level="INFO") as logs:
            self.assertEqual(extract_qwen(Path("sample.mp4"), 45, "fake", url, task_id="test-task")["facts"], [])
        self.assertEqual(post.call_args.args, ("POST", url))
        payload = json.loads(post.call_args.kwargs["content"])
        self.assertEqual(payload["model"], "qwen3.8-omni-flash")
        self.assertEqual(payload["modalities"], ["text"])
        self.assertEqual(payload["messages"][0]["content"][0]["type"], "video_url")
        self.assertNotIn("tools", payload)
        self.assertFalse(post.call_args.kwargs["follow_redirects"])
        timeout = post.call_args.kwargs["timeout"]
        self.assertEqual((timeout.connect, timeout.write, timeout.read), (15, 60, 120))
        for detail in ("task_id=test-task", "clip_bytes=7", "request_bytes=", "http_status=200", "phase=first_event", "phase=done", "write_timeout_s=60"):
            self.assertIn(detail, "\n".join(logs.output))

    @patch("httpx.stream")
    @patch.object(Path, "stat")
    @patch.object(Path, "read_bytes", return_value=b"secret-video-content")
    def test_logs_transport_phase_without_request_body_or_credentials(self, _, stat, post):
        stat.return_value.st_size = 20
        url = qwen_endpoint("private-workspace", "cn-beijing")
        post.side_effect = httpx.WriteTimeout("secret-in-exception")
        post.side_effect.__cause__ = TimeoutError("secret-in-cause")
        with (self.assertLogs("uvicorn.error.qwen", level="INFO") as logs,
              self.assertRaisesRegex(ValueError, "上传片段时")):
            extract_qwen(Path("sample.mp4"), 45, "secret-key", url, task_id="local-task")
        text = "\n".join(logs.output)
        self.assertIn("phase=await_headers reason=transport errors=WriteTimeout>TimeoutError", text)
        for secret in ("secret", "private-workspace"):
            self.assertNotIn(secret, text)

    @patch("httpx.stream")
    @patch.object(Path, "stat")
    @patch.object(Path, "read_bytes", return_value=b"fixture")
    def test_stream_interruption_logs_status_and_event_count(self, _, stat, post):
        stat.return_value.st_size = 7
        reply = post.return_value.__enter__.return_value
        reply.is_success, reply.status_code = True, 200
        def broken_stream():
            yield 'data: {"choices":[]}'
            raise httpx.RemoteProtocolError("do not log this response body")
        reply.iter_lines.side_effect = broken_stream
        with (self.assertLogs("uvicorn.error.qwen", level="INFO") as logs,
              self.assertRaisesRegex(ValueError, "读取流式回复时")):
            extract_qwen(Path("sample.mp4"), 45, "fake", qwen_endpoint("ws-test", "cn-beijing"))
        text = "\n".join(logs.output)
        self.assertIn("http_status=200", text)
        self.assertIn("phase=read_stream reason=transport errors=RemoteProtocolError events=1", text)
        self.assertNotIn("do not log", text)

    def test_qwen_endpoint_rejects_non_workspace_host(self):
        with self.assertRaises(ValueError):
            qwen_endpoint("bad.example/path", "cn-beijing")
