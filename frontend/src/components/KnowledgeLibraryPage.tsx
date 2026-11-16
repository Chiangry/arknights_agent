import { useState } from 'react';
import {
  ChevronRight,
  Layers,
  MessageSquareText,
  Plus,
  Search,
} from 'lucide-react';
import { KnowledgeCategory, StrategyVideo } from '../types/strategy';
import { ResilientImage } from './ResilientImage';
import { DEMO_MODE } from '../data/backendPresentation';

interface KnowledgeLibraryPageProps {
  videos: StrategyVideo[];
  onInspectVideo: (videoId: string) => void;
  onAskAboutVideo: (video: StrategyVideo) => void;
  onGoToIngest: () => void;
}

const CATEGORY_TABS: { id: KnowledgeCategory; label: string }[] = [
  { id: 'all', label: '全部分区' },
  { id: 'main', label: '主线与活动' },
  { id: 'roguelike', label: '集成战略' },
  { id: 'cc', label: '危机合约' },
  { id: 'operator', label: '干员测评' },
];

export function KnowledgeLibraryPage({
  videos,
  onInspectVideo,
  onAskAboutVideo,
  onGoToIngest,
}: KnowledgeLibraryPageProps) {
  const [selectedCategory, setSelectedCategory] = useState<KnowledgeCategory>('all');
  const [keyword, setKeyword] = useState<string>('');

  const filtered = videos.filter((video) => {
    const matchesCat =
      selectedCategory === 'all' ? true : !video.backend && video.category === selectedCategory;
    const q = keyword.trim().toLowerCase();
    const matchesQuery =
      !q ||
      video.title.toLowerCase().includes(q) ||
      video.stageCode.toLowerCase().includes(q) ||
      video.creator.toLowerCase().includes(q) ||
      video.bvId.toLowerCase().includes(q) ||
      video.operators.some((op) => op.toLowerCase().includes(q));
    return matchesCat && matchesQuery;
  });

  const totalChunks = videos.reduce((acc, v) => acc + v.chunkCount, 0);
  const totalKeyframes = videos.reduce((acc, v) => acc + v.keyframeCount, 0);

  return (
    <div className="space-y-6">
      {/* Header Summary Card */}
      <section className="glass-panel-elevated rounded-2xl p-6 sm:p-7 relative overflow-hidden">
        <div
          aria-hidden="true"
          className="absolute top-0 left-8 right-8 h-[2px] bg-gradient-to-r from-transparent via-[#17D1FF] to-transparent opacity-80"
        />

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs text-slate-500 font-mono tabular-nums mb-1.5">
              <span>{videos.length} 部攻略视频</span>
              <span aria-hidden="true">·</span>
              <span>{totalChunks} 个语义片段</span>
              <span aria-hidden="true">·</span>
              <span>{DEMO_MODE ? `${totalKeyframes} 帧站位网格` : '关键帧暂未接入'}</span>
            </div>
            <h1 className="text-2xl sm:text-[28px] font-semibold tracking-tight text-slate-950 text-balance">
              攻略切片知识库
            </h1>
          </div>

          <button
            type="button"
            onClick={onGoToIngest}
            className="ark-chamfer-sm inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF] transition-colors whitespace-nowrap shrink-0 cursor-pointer w-fit"
          >
            <Plus className="w-4 h-4" />
            导入新攻略视频
          </button>
        </div>

        {/* Filter Bar */}
        <div className="mt-6 pt-5 border-t border-slate-200/70 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-1 p-1 glass-subsurface rounded-xl w-fit">
            {CATEGORY_TABS.map((tab) => {
              const active = selectedCategory === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  disabled={!DEMO_MODE && tab.id !== 'all'}
                  title={!DEMO_MODE && tab.id !== 'all' ? '分区元数据暂未接入' : undefined}
                  onClick={() => setSelectedCategory(tab.id)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
                    active
                      ? 'bg-white text-slate-950 shadow-sm'
                      : 'text-slate-600 hover:text-slate-950'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          <div className="relative w-full lg:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="按干员名、关卡或作者搜索切片…"
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-white/80 border border-slate-200/80 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[#17D1FF]"
              aria-label="搜索攻略切片库"
            />
          </div>
        </div>
      </section>

      {/* Clean Glass Table View */}
      <section className="glass-panel rounded-2xl overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <Layers className="w-7 h-7 text-slate-400 mx-auto" />
            <p className="text-sm font-medium text-slate-800">没有匹配的攻略档案</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200/75 text-xs text-slate-500 font-medium bg-white/40">
                  <th className="py-3.5 pl-6 pr-4 font-medium whitespace-nowrap">攻略视频</th>
                  <th className="py-3.5 px-4 font-medium whitespace-nowrap">分区 / 关卡</th>
                  <th className="py-3.5 px-4 font-medium whitespace-nowrap">核心干员实体</th>
                  <th className="py-3.5 px-4 font-medium text-right whitespace-nowrap">切片 / 关键帧</th>
                  <th className="py-3.5 pl-4 pr-6 font-medium text-right whitespace-nowrap">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/60 text-sm">
                {filtered.map((video) => (
                  <tr
                    key={video.id}
                    className="hover:bg-white/60 transition-colors duration-150"
                  >
                    <td className="py-4 pl-6 pr-4 min-w-[300px]">
                      <div className="flex items-center gap-3.5">
                        <div className="w-24 aspect-video rounded-lg overflow-hidden bg-slate-100 shrink-0">
                          <ResilientImage
                            src={video.thumbnail}
                            alt={video.title}
                            className="w-full h-full object-cover"
                            fallbackLabel={video.stageCode}
                          />
                        </div>
                        <div className="min-w-0">
                          <button
                            type="button"
                            onClick={() => onInspectVideo(video.id)}
                            className="text-left text-[13px] sm:text-sm font-semibold text-slate-900 hover:text-[#008DB3] transition-colors line-clamp-1 cursor-pointer"
                          >
                            {video.title}
                          </button>
                          <div className="text-xs text-slate-500 font-mono tabular-nums mt-0.5">
                            {[video.creator, video.publishedAt || (video.indexedAt && `入库 ${video.indexedAt}`), video.bvId, video.duration].filter(Boolean).join(' · ')}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-4 px-4 whitespace-nowrap">
                      <div className="text-xs font-semibold text-[#008DB3] font-mono">
                        {video.stageCode}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {video.categoryLabel}
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <div className="text-xs text-slate-700 max-w-[240px] truncate">
                        {video.backend ? '—' : video.operators.join(' · ')}
                      </div>
                    </td>
                    <td className="py-4 px-4 text-right font-mono tabular-nums whitespace-nowrap">
                      <div className="text-xs font-semibold text-slate-900">
                        {video.chunkCount} 切片
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {video.backend ? '—' : `${video.keyframeCount} 帧`}
                      </div>
                    </td>
                    <td className="py-4 pl-4 pr-6 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => onInspectVideo(video.id)}
                          className="inline-flex items-center gap-0.5 text-xs font-medium text-slate-600 hover:text-slate-950 transition-colors cursor-pointer"
                        >
                          详情
                          <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onAskAboutVideo(video)}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-[#008DB3] hover:text-slate-950 transition-colors cursor-pointer"
                        >
                          <MessageSquareText className="w-3.5 h-3.5" />
                          以此提问
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
