import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from faster_whisper import WhisperModel

audio = "data/tmp_audio/BV1n9uq6NEWu.m4a"
t0 = time.time()
model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
print(f"模型加载耗时: {time.time()-t0:.1f}s")

t1 = time.time()
segments, info = model.transcribe(audio, language="zh", vad_filter=True)
n = 0
last = 0.0
for seg in segments:
    n += 1
    last = seg.end
dt = time.time() - t1
print(f"音频时长: {info.duration:.1f}s ({info.duration/60:.1f}分钟)")
print(f"转写耗时: {dt:.1f}s, 片段数: {n}")
print(f"速度倍率: {info.duration/dt:.2f}x (越大越快)")
print(f"即每分钟音频约需: {dt/(info.duration/60):.1f}s")
