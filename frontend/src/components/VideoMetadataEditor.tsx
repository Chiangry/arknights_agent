import { useState } from 'react';
import { useCatalog } from '../hooks/useCatalog';
import { updateVideo, refreshVideoMetadata } from '../api/videos';
import type { StrategyVideo } from '../types/strategy';
import type { VideoMetadata } from '../types/backend';

export function VideoMetadataEditor({ video, onSaved }: { video: StrategyVideo; onSaved: () => Promise<void> }) {
  const { games, error: catalogError } = useCatalog();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const initial = (): VideoMetadata => ({ title: video.title, author: video.creator === '未知作者' ? '' : video.creator,
    game_id: video.game || null, category_id: video.category === 'unknown' ? null : video.category, stage_name: video.stageCode });
  const [draft, setDraft] = useState(initial);
  const inputClass = 'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:border-[#17D1FF]';
  if (!editing) return <div className="space-y-2">
    <button type="button" disabled={busy} className="text-sm text-[#008DB3] mr-4" onClick={() => { setDraft(initial()); setNotice(''); setEditing(true); }}>编辑视频信息</button>
    {video.bvId.startsWith('BV') && <button type="button" disabled={busy} className="text-sm text-[#008DB3] disabled:opacity-40" onClick={async () => {
      setBusy(true); setNotice('');
      try { await refreshVideoMetadata(video.id); await onSaved(); setNotice('已补全缺失的平台信息，未覆盖手动编辑内容。'); }
      catch (err) { setNotice(err instanceof Error ? err.message : '补全失败'); }
      finally { setBusy(false); }
    }}>{busy ? '读取中…' : '补全 B 站信息'}</button>}
    {notice && <p role="status" className="text-xs text-slate-600">{notice}</p>}
  </div>;
  return <form className="space-y-3 rounded-xl border border-slate-200 p-4" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setNotice('');
    try { await updateVideo(video.id, draft); await onSaved(); setEditing(false); setNotice('已保存，分类立即用于检索，无需重新转写。'); }
    catch (err) { setNotice(err instanceof Error ? err.message : '保存失败'); }
    finally { setBusy(false); }
  }}>
    <fieldset disabled={busy} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <label className="text-xs space-y-1">标题<input required maxLength={300} className={inputClass} value={draft.title || ''} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
      <label className="text-xs space-y-1">作者<input maxLength={200} className={inputClass} value={draft.author || ''} onChange={e => setDraft({ ...draft, author: e.target.value })} /></label>
      <label className="text-xs space-y-1">游戏<select className={inputClass} value={draft.game_id || ''} onChange={e => setDraft({ ...draft, game_id: e.target.value as VideoMetadata['game_id'] || null, category_id: null })}>
        <option value="">未知／未分类</option>{games.map(g => <option key={g.id} value={g.id}>{g.label}</option>)}
      </select></label>
      <label className="text-xs space-y-1">分类<select className={inputClass} value={draft.category_id || ''} onChange={e => setDraft({ ...draft, category_id: e.target.value || null })}>
        <option value="">暂不分类</option>{games.find(g => g.id === draft.game_id)?.categories.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
      </select></label>
      <label className="text-xs space-y-1 sm:col-span-2">关卡／区域<input maxLength={200} className={inputClass} value={draft.stage_name || ''} onChange={e => setDraft({ ...draft, stage_name: e.target.value || null })} /></label>
    </fieldset>
    {(notice || catalogError) && <p role="alert" className="text-xs text-rose-600">{notice || catalogError}</p>}
    <div className="flex gap-3"><button disabled={busy || !games.length} className="px-3 py-2 rounded-lg bg-[#17D1FF] text-xs disabled:opacity-40">{busy ? '保存中…' : '保存信息'}</button>
      <button type="button" disabled={busy} className="text-xs" onClick={() => setEditing(false)}>取消</button></div>
  </form>;
}
