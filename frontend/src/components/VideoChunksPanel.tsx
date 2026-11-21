import { useEffect, useState } from 'react';
import { fetchVideoChunks } from '../api/videos';
import { biliUrl, timecode } from '../data/backendPresentation';
import type { StoredVideoChunk } from '../types/backend';

const PAGE_SIZE = 20;

export function VideoChunksPanel({ videoId, chunkCount }: { videoId: string; chunkCount: number }) {
  const [input, setInput] = useState('');
  const [view, setView] = useState({ query: '', page: 0, attempt: 0 });
  const [items, setItems] = useState<StoredVideoChunk[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const button = 'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:border-[#17D1FF] disabled:cursor-not-allowed disabled:opacity-40';

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    fetchVideoChunks(videoId, view.query, PAGE_SIZE, view.page * PAGE_SIZE, controller.signal)
      .then(result => {
        if (controller.signal.aborted) return;
        const lastPage = Math.max(0, Math.ceil(result.total / PAGE_SIZE) - 1);
        if (view.page > lastPage) {
          setView(v => ({ ...v, page: lastPage }));
          return;
        }
        setItems(result.chunks);
        setTotal(result.total);
        setLoading(false);
      })
      .catch(err => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : '无法读取视频切片');
        setLoading(false);
      });
    return () => controller.abort();
  }, [videoId, view, chunkCount]);

  const filter = (query: string) => {
    setLoading(true);
    setView(v => ({ query: query.trim(), page: 0, attempt: v.attempt + 1 }));
  };
  const changePage = (page: number) => {
    setLoading(true);
    setView(v => ({ ...v, page }));
  };

  return (
    <section className="border-t border-slate-200/70 pt-5 space-y-3" aria-label="已入库切片">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">已入库切片</h3>
        <p className="mt-1 text-xs text-slate-500">直接查看存进索引的正文，按视频时间排列；不经过问答召回或相邻片段合并。</p>
      </div>
      <form className="flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); filter(input); }}>
        <input type="search" aria-label="搜索切片正文" placeholder="例如：明河、充能轴" value={input}
          maxLength={200} onChange={e => setInput(e.target.value)}
          className="min-w-36 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm focus:border-[#17D1FF] focus:outline-none" />
        <button type="submit" className={button}>搜索切片</button>
        {view.query && <button type="button" className={button} onClick={() => { setInput(''); filter(''); }}>清除</button>}
      </form>
      <div aria-busy={loading}>
        {loading ? <p role="status" className="text-xs text-slate-500">正在读取已入库切片…</p>
          : error ? <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-rose-700">
            {error}<button type="button" className={button} onClick={() => setView(v => ({ ...v, attempt: v.attempt + 1 }))}>重试</button>
          </div>
          : !total ? <p role="status" className="text-xs text-slate-500">
            {view.query ? '没有包含该关键词的切片。' : '这条视频尚无已入库切片。'}
          </p>
          : <>
            <p role="status" className="mb-2 text-xs tabular-nums text-slate-500">
              {view.query ? `命中 ${total} 条切片` : `共 ${total} 条切片`}
            </p>
            <ol className="divide-y divide-slate-200/70">
              {items.map(chunk => {
                const sourceLink = chunk.start_sec == null ? undefined : biliUrl(videoId, chunk.start_sec);
                return <li key={chunk.id} className="space-y-2 py-3">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                    <span className="font-medium text-slate-700">切片 #{chunk.chunk_idx + 1}</span>
                    <span className="font-mono tabular-nums">
                      {chunk.start_sec == null ? '—' : timecode(chunk.start_sec)}–{chunk.end_sec == null ? '—' : timecode(chunk.end_sec)}
                    </span>
                    <span>{chunk.source || '来源未标注'}</span>
                    {sourceLink && <a href={sourceLink} target="_blank" rel="noreferrer" className="text-[#008DB3] hover:underline">跳到原视频</a>}
                  </div>
                  <p className="text-sm leading-relaxed whitespace-pre-wrap break-words text-slate-800">{chunk.text}</p>
                </li>;
              })}
            </ol>
            {total > PAGE_SIZE && <div className="flex items-center justify-between gap-2 border-t border-slate-200/70 pt-3">
              <button type="button" className={button} disabled={view.page === 0} onClick={() => changePage(view.page - 1)}>上一页</button>
              <span className="text-xs tabular-nums text-slate-500">第 {view.page + 1} / {Math.ceil(total / PAGE_SIZE)} 页</span>
              <button type="button" className={button} disabled={(view.page + 1) * PAGE_SIZE >= total} onClick={() => changePage(view.page + 1)}>下一页</button>
            </div>}
          </>}
      </div>
    </section>
  );
}
