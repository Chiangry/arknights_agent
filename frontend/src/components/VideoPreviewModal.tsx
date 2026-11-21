import { X, Play, Clock, Layers, MessageSquareText } from 'lucide-react';
import { useState } from 'react';
import { StrategyVideo } from '../types/strategy';
import { ResilientImage } from './ResilientImage';
import { biliUrl } from '../data/backendPresentation';
import { VideoMetadataEditor } from './VideoMetadataEditor';
import { VideoChunksPanel } from './VideoChunksPanel';
import { VideoVisualCoverage } from './VideoVisualCoverage';

interface VideoPreviewModalProps {
  video: StrategyVideo | null;
  highlightTimestamp?: string;
  onClose: () => void;
  onAskAboutVideo: (video: StrategyVideo) => void;
  onMetadataSaved: () => Promise<void>;
  onDeleteVideo: (videoId: string) => Promise<void>;
  onSupplementVideo: (video: StrategyVideo) => Promise<void>;
}

export function VideoPreviewModal({
  video,
  highlightTimestamp,
  onClose,
  onAskAboutVideo,
  onMetadataSaved,
  onDeleteVideo,
  onSupplementVideo,
}: VideoPreviewModalProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [supplementing, setSupplementing] = useState(false);
  const [supplementError, setSupplementError] = useState('');
  if (!video) return null;
  const close = () => { if (!deleting) onClose(); };
  const canDelete = video.backend && !video.taskId && video.status === 'indexed';
  const seconds = highlightTimestamp?.split(':').reduce((acc, n) => acc * 60 + Number(n), 0);
  const link = video.sourceUrl && biliUrl(video.bvId, seconds);

  const isEndfield = video.game === 'endfield';
  const accentTextClass = isEndfield ? 'text-[#9A7400]' : 'text-[#008DB3]';
  const overlayTimeTextClass = isEndfield ? 'text-[#FFE600]' : 'text-cyan-200';
  const ctaButtonClass = isEndfield
    ? 'bg-[#FFE600] text-[#18181B] hover:bg-[#F5D800]'
    : 'bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF]';
  const highlightBgClass = isEndfield ? 'bg-[#FFE600]/18' : 'bg-[#17D1FF]/12';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/25 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="video-modal-title"
      onClick={close}
    >
      <div
        className="w-full max-w-3xl max-h-[calc(100dvh-2rem)] flex flex-col glass-panel-elevated rounded-2xl overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200/70 flex items-center justify-between gap-4 shrink-0">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 font-mono tabular-nums">
              <span className="font-semibold text-slate-800">{video.gameLabel}</span>
              <span aria-hidden="true">·</span>
              <span className={`${accentTextClass} font-semibold`}>{video.stageCode}</span>
              <span aria-hidden="true">·</span>
              <span>{video.creator}</span>
              {(video.publishedAt || video.indexedAt) && <>
                <span aria-hidden="true">·</span>
                <span>{video.publishedAt ? `发布于 ${video.publishedAt}` : `入库于 ${video.indexedAt}`}</span>
              </>}
              <span aria-hidden="true">·</span>
              <span>{video.bvId}</span>
            </div>
            <h2
              id="video-modal-title"
              className="mt-1 text-base sm:text-lg font-semibold text-slate-900 truncate"
            >
              {video.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={deleting}
            aria-label="关闭视频切片预览"
            className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100/80 transition-colors cursor-pointer shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Visual Frame & Metadata */}
        <div className="p-6 space-y-6 min-h-0 overflow-y-auto">
          <div className="relative aspect-video rounded-xl overflow-hidden bg-slate-100">
            <ResilientImage
              src={video.thumbnail}
              alt={video.title}
              className="w-full h-full object-cover"
              fallbackLabel={video.stageCode}
            />
            <div className="absolute inset-0 bg-gradient-to-t from-slate-950/75 via-slate-950/15 to-transparent" />
            <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between gap-4 text-white">
              <div className="flex items-center gap-3">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center shadow-lg ${
                    isEndfield
                      ? 'bg-[#FFE600] text-[#18181B]'
                      : 'bg-[#17D1FF] text-[#071B26]'
                  }`}
                >
                  <Play className="w-4 h-4 fill-current ml-0.5" />
                </div>
                <div>
                  <p className={`text-xs font-mono tabular-nums ${overlayTimeTextClass}`}>
                    {highlightTimestamp
                      ? `已定位至引用时间轴 · ${highlightTimestamp}`
                      : `总时长 · ${video.duration}`}
                  </p>
                  <p className="text-sm font-medium text-white/95">
                    {video.categoryLabel} · {video.chunkCount} 个语义向量切片
                  </p>
                </div>
              </div>
              {!video.backend && <span className="text-xs font-mono tabular-nums text-white/85">
                {video.keyframeCount} 关键帧已校准
              </span>}
            </div>
          </div>

          {/* Summary & Operators */}
          {video.backend && !video.taskId && <VideoMetadataEditor key={video.id} video={video} onSaved={onMetadataSaved} />}
          {video.backend && !video.taskId && link && <div className="space-y-1">
            <button type="button" disabled={supplementing || deleting || confirmDelete}
              className="text-sm text-[#008DB3] disabled:opacity-50"
              onClick={async () => {
                setSupplementing(true);
                setSupplementError('');
                try { await onSupplementVideo(video); }
                catch (err) { setSupplementError(err instanceof Error ? err.message : '无法启动画面抽样'); }
                finally { setSupplementing(false); }
              }}>{supplementing ? '正在提交…' : '继续解析全片画面'}</button>
            {supplementError && <p role="alert" className="text-xs text-rose-700">{supplementError}</p>}
          </div>}
          {video.backend && !video.taskId && link && <VideoVisualCoverage videoId={video.id} />}
          {video.backend ? (
            <div className="space-y-2 text-sm text-slate-700">
              <p>{video.progressStage || video.summary}</p>
            </div>
          ) : <div className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-900">攻略核心摘要</h3>
            <p className="text-sm leading-relaxed text-slate-600">{video.summary}</p>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500 pt-1">
              <span className="font-medium text-slate-700">
                {isEndfield ? '关联干员 / 设施实体：' : '关联干员实体：'}
              </span>
              {video.operators.map((op, index) => (
                <span key={op} className="inline-flex items-center gap-2">
                  <span className="text-slate-800 font-medium">{op}</span>
                  {index < video.operators.length - 1 && <span aria-hidden="true">/</span>}
                </span>
              ))}
            </div>
          </div>}

          {video.backend && !video.taskId && <VideoChunksPanel videoId={video.id} chunkCount={video.chunkCount} />}

          {/* Extracted Keyframe Timeline */}
          {!video.backend && <div className="border-t border-slate-200/70 pt-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <Layers className={`w-4 h-4 ${accentTextClass}`} />
                已提取的高光战术时间轴
              </h3>
              <span className="text-xs text-slate-500 font-mono tabular-nums">
                共 {video.extractedHighlights.length} 个核心节点
              </span>
            </div>
            <div className="divide-y divide-slate-200/60">
              {video.extractedHighlights.map((item) => {
                const isTarget = highlightTimestamp === item.timestamp;
                return (
                  <div
                    key={item.timestamp}
                    className={`py-3 px-3 rounded-xl transition-colors flex items-start gap-4 ${
                      isTarget ? highlightBgClass : 'hover:bg-slate-50/70'
                    }`}
                  >
                    <span
                      className={`inline-flex items-center gap-1.5 text-xs font-mono tabular-nums font-semibold pt-0.5 shrink-0 ${accentTextClass}`}
                    >
                      <Clock className="w-3.5 h-3.5" />
                      {item.timestamp}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-900">{item.title}</p>
                      <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{item.detail}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>}
        </div>

        {/* Footer Action */}
        <div className="px-6 py-4 border-t border-slate-200/70 bg-white/40 space-y-3 shrink-0">
          {confirmDelete && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 space-y-2">
              <p className="text-sm text-slate-800">确定从知识库删除《{video.title}》？</p>
              <p className="text-xs text-slate-600">视频档案、字幕与画面切片及其向量将一并删除，无法撤销。不会删除 B 站原视频、本地原文件或聊天记录。</p>
              {deleteError && <p role="alert" className="text-xs text-rose-700">{deleteError}</p>}
              <div className="flex gap-3">
                <button type="button" disabled={deleting} className="px-3 py-2 rounded-lg text-xs hover:bg-white"
                  onClick={() => setConfirmDelete(false)}>取消</button>
                <button type="button" disabled={deleting}
                  className="px-3 py-2 rounded-lg bg-rose-700 text-white text-xs hover:bg-rose-800 disabled:opacity-60"
                  onClick={async () => {
                    setDeleting(true);
                    setDeleteError('');
                    try { await onDeleteVideo(video.id); }
                    catch (err) { setDeleteError(err instanceof Error ? err.message : '删除失败，请重试'); }
                    finally { setDeleting(false); }
                  }}>{deleting ? '正在删除…' : '确认删除'}</button>
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
          {canDelete && !confirmDelete ? <button type="button"
            className="px-2 py-2 text-xs font-medium text-rose-700 hover:underline"
            onClick={() => { setDeleteError(''); setConfirmDelete(true); }}>删除入库视频</button> : <span />}
          <div className="flex flex-wrap items-center gap-3">
            {link && <a href={link} target="_blank" rel="noreferrer" className="text-xs font-semibold text-[#007894] hover:underline">打开 B 站原视频</a>}
            <button
              type="button"
              onClick={close}
              disabled={deleting}
              className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100/80 transition-colors cursor-pointer whitespace-nowrap"
            >
              关闭
            </button>
            <button
              type="button"
              disabled={deleting || confirmDelete || (video.backend && video.status !== 'indexed')}
              onClick={() => {
                onAskAboutVideo(video);
                onClose();
              }}
              className={`ark-chamfer-sm inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${ctaButtonClass}`}
            >
              <MessageSquareText className="w-3.5 h-3.5" />
              针对此攻略提问
            </button>
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}
