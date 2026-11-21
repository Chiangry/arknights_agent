import { useEffect, useState } from 'react';
import { fetchVisualCoverage } from '../api/videos';
import { timecode } from '../data/backendPresentation';
import type { VisualWindow } from '../types/backend';

export function VisualWindows({ windows }: { windows: VisualWindow[] }) {
  if (!windows.length) return null;
  return <details className="text-xs text-slate-600">
    <summary className="cursor-pointer">查看各时段状态</summary>
    <ul className="mt-2 space-y-1">
      {windows.map(w => <li key={`${w.start}:${w.end}`}>
        {timecode(w.start)}–{timecode(w.end)} · {w.status === 'indexed' ? '有证据' : w.status === 'empty' ? '无可用证据' : `失败：${w.reason || '异常'}`}
      </li>)}
    </ul>
  </details>;
}

export function VideoVisualCoverage({ videoId }: { videoId: string }) {
  const [report, setReport] = useState<{ duration: number | null; windows: VisualWindow[] }>();
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetchVisualCoverage(videoId, controller.signal)
      .then(result => { if (!controller.signal.aborted) setReport(result); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [videoId]);
  if (error) return <p role="alert" className="text-xs text-rose-700">{error}</p>;
  if (!report?.windows.length) return null;
  const failed = report.windows.filter(w => w.status === 'failed').length;
  const covered = report.windows.filter(w => w.status !== 'failed').reduce((sum, w) => sum + w.end - w.start, 0);
  return <section className="space-y-2">
    <p className="text-xs text-slate-600">画面已检查 {timecode(covered)}{report.duration ? ` / ${timecode(report.duration)}` : ''}，失败 {failed} 段。继续解析只处理尚未完成的时段。</p>
    <VisualWindows windows={report.windows} />
  </section>;
}
