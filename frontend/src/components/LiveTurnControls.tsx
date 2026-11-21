import { useState } from 'react';
import { Check, Database, Globe, Sparkles } from 'lucide-react';
import { confirmAudio, type AudioConfirmation, type ExternalSearchDetails } from '../api/qa';
import { setTaskPaused } from '../api/videos';
import { biliUrl } from '../data/backendPresentation';
import type { AudioImportOption, ExternalVideo } from '../types/backend';
import type { StrategyVideo } from '../types/strategy';
import { ResilientImage } from './ResilientImage';

const actionClass = 'rounded-lg px-3 py-1.5 text-xs font-semibold bg-white/70 text-slate-700 hover:bg-white disabled:opacity-40';
const primaryClass = 'ark-chamfer-sm px-4 py-2 inline-flex items-center gap-1.5 text-xs font-semibold bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF] disabled:opacity-45 disabled:cursor-not-allowed';
const panelClass = 'glass-panel min-w-0 max-w-full rounded-2xl p-4 sm:p-5 space-y-3 text-xs text-slate-700';

type SearchVideo = AudioConfirmation['videos'][number] & { cover?: string };

function CandidateRow({ video, checked, disabled, onToggle }: {
  video: SearchVideo;
  checked?: boolean;
  disabled?: boolean;
  onToggle?: () => void;
}) {
  const selectable = !!onToggle;
  const meta = [
    video.author || '作者未知',
    video.pubdate ? new Date(video.pubdate * 1000).toLocaleDateString('zh-CN') : '发布日期未知',
    video.bvid,
    video.play != null ? `${video.play.toLocaleString('zh-CN')} 播放` : '',
  ].filter(Boolean).join(' · ');
  return (
    <div className={`relative flex min-w-0 items-center gap-3 overflow-hidden rounded-xl border p-2.5 sm:p-3 transition-colors ${checked
      ? 'bg-white border-[#17D1FF] shadow-sm' : 'bg-white/55 border-slate-200/75 hover:bg-white/85'}`}>
      {selectable && (
        <label className="flex shrink-0 items-center cursor-pointer">
          <input type="checkbox" aria-label={`选择 ${video.title}`} checked={!!checked} disabled={disabled}
            onChange={onToggle} className="peer sr-only" />
          <span aria-hidden="true" className={`flex size-5 items-center justify-center rounded-md peer-focus-visible:ring-2 peer-focus-visible:ring-[#17D1FF] ${checked
            ? 'bg-[#17D1FF] text-[#071B26]' : 'border border-slate-300 bg-white'}`}>
            {checked && <Check className="size-3.5 stroke-[2.5]" />}
          </span>
        </label>
      )}
      <a href={biliUrl(video.bvid)} target="_blank" rel="noreferrer" className="relative w-20 sm:w-24 aspect-video rounded-lg overflow-hidden bg-slate-100 shrink-0">
        <ResilientImage src={video.cover || ''} alt={video.title} className="w-full h-full object-cover" fallbackLabel="B 站" />
        {video.duration && <span className="absolute bottom-1 right-1 px-1 rounded bg-slate-950/75 text-[10px] font-mono text-white">{video.duration}</span>}
      </a>
      <div className="min-w-0 flex-1 overflow-hidden">
        <a href={biliUrl(video.bvid)} target="_blank" rel="noreferrer"
          title={video.title}
          className="text-[13px] font-semibold text-slate-900 line-clamp-2 [overflow-wrap:anywhere] hover:text-[#008DB3]">{video.title}</a>
        <div title={meta} className="mt-1 truncate text-[11px] text-slate-500 font-mono">{meta}</div>
        {video.description && <p title={video.description} className="mt-1 truncate text-[11px] text-slate-600">{video.description}</p>}
      </div>
    </div>
  );
}

function SearchHeading({ details, count, selection }: { details?: ExternalSearchDetails; count: number; selection?: number }) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-950">
          <Globe className="size-4 text-[#008DB3]" /> B 站搜索结果
        </h3>
        <span className="font-mono tabular-nums text-slate-500">
          {selection == null ? `${count} 部候选` : `已勾选 ${selection} / ${count}`}
        </span>
      </div>
      {details?.reason && <p className="text-slate-600">{details.reason}</p>}
      {!!details?.missing?.length && <p className="text-slate-500">待补充：{details.missing.join('、')}</p>}
    </div>
  );
}

export function AudioChoice({ taskId, confirmation, candidates, details, selected, onToggle, onDecision }: {
  taskId: string;
  confirmation: AudioConfirmation;
  candidates?: ExternalVideo[];
  details?: ExternalSearchDetails;
  selected: string[];
  onToggle: (bvid: string) => void;
  onDecision: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function decide(bvids: string[]) {
    setBusy(true);
    setError('');
    try { await confirmAudio(taskId, bvids); onDecision(); }
    catch (err) { setError(err instanceof Error ? err.message : '确认失败'); }
    finally { setBusy(false); }
  }
  return (
    <section className={panelClass} aria-label="转写确认">
      <SearchHeading details={details} count={confirmation.videos.length} selection={selected.length} />
      <p>是否下载并转写这些音轨？每部最多 {confirmation.max_mib_per_video} MiB，确认窗口 {confirmation.timeout_seconds} 秒。</p>
      <div className="grid grid-cols-1 gap-2.5">
        {confirmation.videos.map(video => (
          <CandidateRow key={video.bvid} video={{ ...candidates?.find(v => v.bvid === video.bvid), ...video }}
            checked={selected.includes(video.bvid)} disabled={busy}
            onToggle={() => onToggle(video.bvid)} />
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200/70 pt-2">
        <button className={actionClass} disabled={busy} onClick={() => void decide([])}>不转写，保留已有结果</button>
        <button className={actionClass} disabled={busy} onClick={() => void decide(confirmation.videos.map(v => v.bvid))}>全部转写</button>
        <button className={primaryClass} disabled={busy || !selected.length} onClick={() => void decide(selected)}>
          <Sparkles className="size-3.5" /> 转写所选 ({selected.length})
        </button>
      </div>
      {error && <p role="alert" className="text-rose-700">{error}</p>}
    </section>
  );
}

export function TranscriptOffer({ videos, tasks, onSave }: {
  videos: AudioImportOption[];
  tasks: Record<string, StrategyVideo | undefined>;
  onSave: (video: AudioImportOption) => Promise<string | undefined>;
}) {
  const mostCited = Math.max(0, ...videos.map(v => v.citation_count));
  const recommended = (v: AudioImportOption) => mostCited > 0 && v.citation_count === mostCited;
  const [selected, setSelected] = useState(videos.filter(recommended).map(v => v.bvid));
  const [results, setResults] = useState<Record<string, { message: string; running?: boolean; done?: boolean }>>({});
  const [dismissed, setDismissed] = useState(false);
  const locked = (id: string) => results[id]?.running || results[id]?.done ||
    (tasks[id] && tasks[id]?.status !== 'error');
  async function save(video: AudioImportOption) {
    const id = video.bvid;
    const write = (result: (typeof results)[string]) => setResults(prev => ({ ...prev, [id]: result }));
    write({ message: '正在提交…', running: true });
    try {
      const task = await onSave(video);
      write(task ? { message: '已提交' } : { message: '已在知识库', done: true });
    } catch (err) { write({ message: err instanceof Error ? err.message : '入库失败' }); }
  }
  if (dismissed) return null;
  const available = videos.filter(v => !locked(v.bvid));
  return (
    <section className={`${panelClass} border border-[#17D1FF]/45`} aria-label="转写视频入库">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong className="inline-flex items-center gap-2 text-[13px] text-slate-950">
          <Database className="size-4 text-[#008DB3]" /> 是否将本次转写的视频加入知识库？
        </strong>
        <span className="font-mono tabular-nums text-slate-500">已选 {available.filter(v => selected.includes(v.bvid)).length} 部</span>
      </div>
      {videos.map(v => {
        const task = tasks[v.bvid];
        return (
          <label key={v.bvid} className="flex min-w-0 items-start gap-2 overflow-hidden p-2 rounded-lg bg-white/65">
            <input type="checkbox" checked={selected.includes(v.bvid)} disabled={!!locked(v.bvid)}
              className="mt-0.5 shrink-0"
              onChange={e => setSelected(s => e.target.checked ? [...s, v.bvid] : s.filter(id => id !== v.bvid))} />
            <span className="min-w-0 flex-1 overflow-hidden">
              <span title={v.title} className="block truncate">{v.title}</span>
              <small className="block truncate">引用 {v.citation_count} 段{recommended(v) ? ' · 推荐入库' : ''}
              {task || results[v.bvid] ? ` · ${results[v.bvid]?.running || results[v.bvid]?.done
                ? results[v.bvid].message : task?.progressStage || results[v.bvid]?.message}` : ''}
            </small></span>
          </label>
        );
      })}
      <div className="flex flex-wrap justify-end gap-2">
        <button className={actionClass} onClick={() => setDismissed(true)}>暂不入库</button>
        <button className={actionClass} disabled={!available.length} onClick={() => available.forEach(v => void save(v))}>全部入库</button>
        <button className={primaryClass} disabled={!available.some(v => selected.includes(v.bvid))}
          onClick={() => available.filter(v => selected.includes(v.bvid)).forEach(v => void save(v))}>确认加入知识库</button>
      </div>
    </section>
  );
}

export function ExternalCandidates({ videos, details, pending }: {
  videos: ExternalVideo[];
  details?: ExternalSearchDetails;
  pending?: boolean;
}) {
  return (
    <section className={panelClass} aria-label="B 站攻略推荐">
      <SearchHeading details={details} count={videos.length} />
      {pending && !!videos.length && <p className="text-slate-500">将先查找可用字幕，下载转写前会征求确认。</p>}
      {videos.length ? <div className="grid grid-cols-1 gap-2.5">
        {videos.map(video => <CandidateRow key={video.bvid} video={video} />)}
      </div> : <p>未找到可用候选。</p>}
    </section>
  );
}

export function PauseAudio({ taskId, paused, message }: { taskId: string; paused: boolean; message: string }) {
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState<boolean>();
  const [error, setError] = useState('');
  const pause = requested ?? paused;
  async function toggle() {
    setBusy(true);
    setError('');
    try {
      const snap = await setTaskPaused(taskId, !pause);
      setRequested(snap.pause_requested);
    } catch (err) { setError(err instanceof Error ? err.message : '未能修改暂停状态'); }
    finally { setBusy(false); }
  }
  const fraction = message.match(/（(\d{1,3})%）/);
  const progress = fraction ? Math.min(100, Number(fraction[1])) : undefined;
  return <section className={panelClass} aria-label="攻略视频转写进度">
    <div className="flex items-center justify-between gap-3">
      <strong className="text-slate-950">{paused ? '已暂停' : '正在解析攻略视频'}</strong>
      {progress != null && <span className="font-mono tabular-nums">{progress}%</span>}
    </div>
    <div className="h-1.5 rounded-full bg-slate-200/80 overflow-hidden" aria-hidden="true">
      <div className={`h-full rounded-full bg-[#17D1FF] transition-all ${progress == null && !paused ? 'animate-pulse w-1/4' : ''}`}
        style={progress == null ? undefined : { width: `${progress}%` }} />
    </div>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-slate-600">{message}</p>
      <button className={actionClass} disabled={busy} onClick={() => void toggle()}>{pause ? '继续转写' : '暂停转写'}</button>
    </div>
    {pause && !paused && <small className="text-slate-500">等待处理边界暂停</small>}
    {error && <small role="alert" className="text-rose-700">{error}</small>}
  </section>;
}
