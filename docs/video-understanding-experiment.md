# 音视频理解对照实验

对同一个短片段运行本地 Whisper 和可选的 Gemini 视频理解。
它不会读取旧转写缓存，不写入数据库，也不会修改正常导入流程。
需要项目 Python 环境、ffmpeg 和 ffprobe。

```sh
python -m scripts.compare_video_understanding --bvid BV1qc4i6aEGQ --start 0 --seconds 45
```

也可用 `--file /path/to/video.mp4` 代替 BV 号。建议选确认出现配队界面和解说的 30–55 秒。
默认不向 Gemini 发送任何内容。确认允许该短片段上传时，在本地 `.env` 设置
`GEMINI_API_KEY`，在命令末尾添加 `--send-to-gemini`。
选中片段以内联视频发送到 Google Gemini API；不会发送整条视频、数据库或旧字幕。
临时视频大小上限 10 MiB，执行结束后自动清理。不启用联网搜索。

也可以用 Qwen3.8-Omni-Flash。把同地域的 `DASHSCOPE_API_KEY`、
`DASHSCOPE_WORKSPACE_ID` 写进本地 `.env`，地域默认为 `cn-beijing`，
新加坡业务空间请设置 `DASHSCOPE_REGION=ap-southeast-1`。命令中加
`--send-to-qwen`（不和 `--send-to-gemini` 同用）。选中的短片段会发送给阿里云百炼，
Base64 后必须小于 10 MB；超过时请缩短样本。仅请求文本输出，不启用联网搜索。

JSON 中 Whisper 是逐段字幕，Gemini／Qwen 是按音频或画面标注来源的候选事实。
所有时间戳均相对片段起点，原视频时间为两者相加。模型能返回更多条目不代表更准确：
应按原片核对角色名单、替换条件、操作顺序，逐项记录正确、遗漏和无证据的内容。
