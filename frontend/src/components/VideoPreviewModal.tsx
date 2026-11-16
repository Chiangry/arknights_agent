import { X, Play, Clock, Layers, MessageSquareText } from 'lucide-react';
import { StrategyVideo } from '../types/strategy';
import { ResilientImage } from './ResilientImage';
import { biliUrl } from '../data/backendPresentation';

interface VideoPreviewModalProps {
  video: StrategyVideo | null;
  highlightTimestamp?: string;
  onClose: () => void;
  onAskAboutVideo: (video: StrategyVideo) => void;
}

export function VideoPreviewModal({
  video,
  highlightTimestamp,
  onClose,
  onAskAboutVideo,
}: VideoPreviewModalProps) {
  if (!video) return null;
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
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl glass-panel-elevated rounded-2xl overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200/70 flex items-center justify-between gap-4">
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
            onClick={onClose}
            aria-label="关闭视频切片预览"
            className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100/80 transition-colors cursor-pointer shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Visual Frame & Metadata */}
        <div className="p-6 space-y-6 max-h-[80vh] overflow-y-auto">
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
          {video.backend ? (
            <div className="space-y-2 text-sm text-slate-700">
              <p>{video.progressStage || video.summary}</p>
              <p className="text-xs text-slate-500">真实视频的关键帧与高光时间轴暂未接入；问答中的引用卡片会显示实际字幕时间。</p>
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
        <div className="px-6 py-4 border-t border-slate-200/70 bg-white/40 flex items-center justify-end gap-4">
          <div className="flex items-center gap-3 shrink-0">
            {link && <a href={link} target="_blank" rel="noreferrer" className="text-xs font-semibold text-[#007894] hover:underline">打开 B 站原视频</a>}
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100/80 transition-colors cursor-pointer whitespace-nowrap"
            >
              关闭
            </button>
            <button
              type="button"
              disabled={video.backend && video.status !== 'indexed'}
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
  );
}
