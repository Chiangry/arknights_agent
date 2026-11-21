import { useState } from 'react';
import { decideVisualUpload } from '../api/videos';
import { timecode } from '../data/backendPresentation';
import type { VisualConfirmation } from '../types/backend';
import type { StrategyVideo } from '../types/strategy';

export function VideoVisualConfirmation({ video, taskId, details }: {
  video: StrategyVideo; taskId: string; details: VisualConfirmation;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const full = details.segment_count != null;
  async function submit(approved: boolean) {
    setPending(true);
    setError('');
    try {
      await decideVisualUpload(taskId, approved);
    } catch (err) {
      setPending(false);
      setError(err instanceof Error ? err.message : '提交失败，请重试');
    }
  }
  return <section aria-label="画面上传确认" className="glass-panel rounded-xl border border-[#17D1FF]/40 p-4 space-y-2">
    <p className="text-sm font-semibold text-slate-900">{full ? '确认全片画面解析？' : '是否上传推荐片段？'}</p>
    <p className="text-sm text-slate-800">{video.title} · {timecode(details.start)}–{timecode(details.start + details.seconds)}</p>
    <p className="text-xs text-slate-600">{full
      ? `确认一次后，系统会自动把剩余 ${details.segment_count} 段静音画面发送给阿里云百炼。音轨不上传；必要时在本地转写。`
      : `${details.reason}。确认后只发送该时段的静音画面给阿里云百炼。`}</p>
    <p className="text-xs text-slate-500">拒绝或约 3 分钟不确认，就不上传；已有字幕和索引保留。</p>
    {error && <p role="alert" className="text-xs text-rose-700">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <button type="button" disabled={pending} onClick={() => void submit(true)}
        className="rounded-lg bg-[#17D1FF] px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50">确认上传并解析</button>
      <button type="button" disabled={pending} onClick={() => void submit(false)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs disabled:opacity-50">不上传</button>
    </div>
  </section>;
}
