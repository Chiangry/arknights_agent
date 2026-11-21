import { useRef, useState } from 'react';
import {
  CheckCircle2,
  Film,
  LayoutGrid,
  Link2,
  List,
  MessageSquareText,
  Search,
  Sparkles,
  UploadCloud,
} from 'lucide-react';
import {
  THUMB_EF_COMBAT,
  THUMB_EF_FACTORY,
  THUMB_OPERATOR,
  THUMB_ROGUELIKE,
  THUMB_STAGE,
} from '../data/mockStrategyData';
import { GameScope, GameTitle, KnowledgeCategory, StrategyVideo } from '../types/strategy';
import { ResilientImage } from './ResilientImage';
import { checkSubtitle, createBiliImport, createLocalImport, searchBilibili, previewVideoMetadata } from '../api/videos';
import { DEMO_MODE, timecode } from '../data/backendPresentation';
import type { ExternalVideo, VideoMetadataPreview } from '../types/backend';
import { useCatalog } from '../hooks/useCatalog';
import { VideoVisualConfirmation } from './VideoVisualConfirmation';
import { VisualWindows } from './VideoVisualCoverage';

interface VideoIngestPageProps {
  videos: StrategyVideo[];
  visualReports: StrategyVideo[];
  onAddVideo: (video: StrategyVideo) => void;
  onTrackTask: (taskId: string, video: StrategyVideo) => void;
  onPauseTask: (taskId: string, paused: boolean) => Promise<void>;
  onInspectVideo: (videoId: string) => void;
  onAskAboutVideo: (video: StrategyVideo) => void;
}

type SourceMode = 'url' | 'file';
type StatusFilter = 'all' | 'processing' | 'indexed';
type ViewMode = 'card' | 'list';

export function VideoIngestPage({
  videos,
  visualReports,
  onAddVideo,
  onTrackTask,
  onPauseTask,
  onInspectVideo,
  onAskAboutVideo,
}: VideoIngestPageProps) {
  const { games, error: catalogError } = useCatalog();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [targetGame, setTargetGame] = useState<GameTitle | null>(DEMO_MODE ? 'arknights' : null);
  const [sourceMode, setSourceMode] = useState<SourceMode>('url');
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [preview, setPreview] = useState<VideoMetadataPreview | null>(null);
  const [videoTitle, setVideoTitle] = useState<string>('');
  const [stageCode, setStageCode] = useState<string>('');
  const [creatorName, setCreatorName] = useState<string>('');
  const [selectedFileName, setSelectedFileName] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File>();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [candidates, setCandidates] = useState<ExternalVideo[]>([]);
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const [category, setCategory] = useState<Exclude<KnowledgeCategory, 'all'>>('unknown');
  const [extractKeyframes, setExtractKeyframes] = useState<boolean>(true);
  const [extractAsr, setExtractAsr] = useState<boolean>(true);
  const [linkOperators, setLinkOperators] = useState<boolean>(true);

  const [gameFilter, setGameFilter] = useState<GameScope>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('card');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [feedbackNotice, setFeedbackNotice] = useState<string>('');

  const isEndfieldForm = targetGame === 'endfield';
  const categoryOptions = [{ id: 'unknown' as const, label: '暂不分类' }, ...(games.find(g => g.id === targetGame)?.categories || [])];

  const currentBvid = videoUrl.match(/BV[0-9A-Za-z]{10}/)?.[0];
  const previewReady = preview != null && currentBvid === preview.bvid;

  const handleSwitchTargetGame = (nextGame: GameTitle | null) => {
    setTargetGame(nextGame);
    setCategory('unknown');
  };

  const resetDraft = () => {
    setPreview(null);
    setVideoTitle('');
    setCreatorName('');
    setStageCode('');
    handleSwitchTargetGame(DEMO_MODE ? 'arknights' : null);
  };

  const changeUrl = (url: string) => {
    if (preview && url.match(/BV[0-9A-Za-z]{10}/)?.[0] !== preview.bvid) {
      resetDraft();
      setFeedbackNotice('');
    }
    setVideoUrl(url);
  };

  const changeSource = (mode: SourceMode) => {
    if (sourceMode === mode) return;
    resetDraft();
    setSelectedFile(undefined);
    setSelectedFileName('');
    setFeedbackNotice('');
    setSourceMode(mode);
  };

  const handleFilePicked = (file: File | undefined) => {
    if (!file) return;
    setSelectedFile(file);
    setSelectedFileName(file.name);
    if (!videoTitle) {
      setVideoTitle(file.name.replace(/\.[^/.]+$/, ''));
    }
    if (DEMO_MODE && !stageCode) {
      setStageCode(isEndfieldForm ? '四号谷地 AIC' : '活动 EX-8 突袭');
    }
    if (!creatorName) {
      setCreatorName('本地录像导入');
    }
  };

  async function runAction(action: () => Promise<void>) {
    setBusy(true);
    setFailed(false);
    setFeedbackNotice('');
    try { await action(); }
    catch (err) {
      setFailed(true);
      setFeedbackNotice(err instanceof Error ? err.message : '操作失败');
    } finally { setBusy(false); }
  }

  const readMetadata = async (url = videoUrl) => {
    if (busy || DEMO_MODE || !url.trim()) return;
    if (preview && url.match(/BV[0-9A-Za-z]{10}/)?.[0] === preview.bvid) {
      setFailed(false);
      setFeedbackNotice('已读取这条视频。可继续编辑，确认后点击解析。');
      return;
    }
    const newVideo = preview != null;
    changeUrl(url);
    await runAction(async () => {
      const info = await previewVideoMetadata(url.trim());
      setPreview(info);
      setVideoTitle(current => newVideo ? (info.title || '') : (current || info.title || ''));
      setCreatorName(current => newVideo ? (info.author || '') : (current || info.author || ''));
      if (newVideo || !targetGame) {
        const game = games.find(item => item.id === info.suggestion.game_id);
        setTargetGame(game?.id || null);
        setCategory(game?.categories.find(item => item.id === info.suggestion.category_id)?.id || 'unknown');
      } else if (targetGame === info.suggestion.game_id && category === 'unknown') {
        setCategory(categoryOptions.find(item => item.id === info.suggestion.category_id)?.id || 'unknown');
      }
      setFeedbackNotice('已读取视频信息。所属作品与分区可编辑，确认后点击解析。');
    });
  };

  const searchCandidates = async () => {
    if (busy || !searchQuery.trim()) return;
    await runAction(async () => {
      const found = await searchBilibili(searchQuery.trim());
      setCandidates(found);
      if (!found.length) setFeedbackNotice('未找到候选视频');
    });
  };

  const handleSubmitIngestion = async () => {
    if (busy) return;
    if (!DEMO_MODE) {
      await runAction(async () => {
        const url = videoUrl.trim();
        if (sourceMode === 'url' && !url) throw new Error('请输入 B 站链接或 BV 号');
        if (sourceMode === 'url' && !previewReady) throw new Error('请先读取这条链接的视频信息');
        if (sourceMode === 'file' && !selectedFile) throw new Error('请先选择文件');
        const metadata = { ...(videoTitle.trim() ? { title: videoTitle.trim() } : {}),
          ...(creatorName.trim() ? { author: creatorName.trim() } : {}),
          game_id: targetGame, category_id: category === 'unknown' ? null : category, stage_name: stageCode.trim() || null };
        const result = sourceMode === 'url' ? await createBiliImport(url, metadata) : await createLocalImport(selectedFile!, metadata);
        const bvId = sourceMode === 'url' ? url.match(/BV[0-9A-Za-z]{10}/)?.[0] || url : '本地文件';
        onTrackTask(result.task_id, {
          id: result.task_id, bvId, title: videoTitle.trim() || result.title || (sourceMode === 'file' ? selectedFileName : bvId),
          creator: creatorName || '待获取', category, categoryLabel: categoryOptions.find(c => c.id === category)?.label || '未分类',
          game: targetGame || undefined, gameLabel: games.find(g => g.id === targetGame)?.label,
          stageCode, duration: preview?.duration_seconds ? timecode(preview.duration_seconds) : '—',
          publishedAt: preview?.published_at ? new Date(preview.published_at).toLocaleDateString('zh-CN') : '',
          thumbnail: preview?.cover_url?.replace(/^http:/, 'https:') || '',
          status: 'queued', progress: 0, progressStage: '排队中', chunkCount: 0,
          operatorCount: 0, keyframeCount: 0, summary: '等待处理', operators: [],
          extractedHighlights: [], backend: true,
        });
        setFeedbackNotice('任务已提交，可以在下方查看实际进度');
        setVideoUrl('');
        resetDraft();
        setSelectedFile(undefined);
        setSelectedFileName('');
        if (fileInputRef.current) fileInputRef.current.value = '';
      });
      return;
    }
    const resolvedTitle =
      videoTitle.trim() ||
      (selectedFileName ? selectedFileName.replace(/\.[^/.]+$/, '') : '') ||
      (isEndfieldForm
        ? '武陵城高阶集成工业产线蓝图 · 息壤精炼配平实录'
        : '14-18 磨难环境 · 双快活控场与高台输出轴实录');
    const resolvedStage =
      stageCode.trim() || (isEndfieldForm ? '武陵枢纽' : '14-18 磨难');
    const resolvedCreator =
      creatorName.trim() || (isEndfieldForm ? '塔卫二管理员存档' : '博士自录存档');
    const bvMatch = videoUrl.match(/BV[0-9A-Za-z]+/i);
    const resolvedBv = bvMatch
      ? bvMatch[0]
      : `BV1${Math.random().toString(36).slice(2, 10).toUpperCase()}`;

    const categoryMeta = categoryOptions.find((c) => c.id === category);
    const thumb = isEndfieldForm
      ? category === 'aic'
        ? THUMB_EF_FACTORY
        : THUMB_EF_COMBAT
      : category === 'roguelike'
      ? THUMB_ROGUELIKE
      : category === 'operator' || category === 'cc'
      ? THUMB_OPERATOR
      : THUMB_STAGE;

    const newVideo: StrategyVideo = {
      id: `vid-${Date.now()}`,
      game: targetGame || 'arknights',
      gameLabel: isEndfieldForm ? '终末地' : '明日方舟',
      bvId: resolvedBv,
      title: resolvedTitle,
      creator: resolvedCreator,
      category,
      categoryLabel: categoryMeta?.label ?? (isEndfieldForm ? '集成工业产线' : '主线与活动'),
      stageCode: resolvedStage,
      duration: '10:36',
      publishedAt: '2026-11-16',
      thumbnail: thumb,
      status: 'processing',
      progress: 24,
      progressStage: extractKeyframes
        ? isEndfieldForm
          ? '工业蓝图与节点识别'
          : '关键帧站位提取'
        : '语音转写与向量切分',
      chunkCount: 14,
      operatorCount: isEndfieldForm ? 4 : 6,
      keyframeCount: 11,
      summary: isEndfieldForm
        ? '已完成产线蓝图节点、技能连携与破韧时间轴提取。'
        : '已完成部署站位关键帧与语音转写对齐，覆盖开局回费与中盘技能轴。',
      operators: isEndfieldForm
        ? ['管理员', '佩丽卡', '陈千语', '余烬']
        : ['伊内丝', '维什戴尔', '玛恩纳', '塞雷娅'],
      extractedHighlights: [
        {
          timestamp: '00:28',
          title: isEndfieldForm ? '核心节点与连携起手' : '开局费用与视野部署',
          detail: isEndfieldForm
            ? '完成主控位起手与核心设施/连携技能衔接。'
            : '先锋前压抢占视野并衔接高台核心输出。',
        },
      ],
    };

    onAddVideo(newVideo);
    setFeedbackNotice(`已加入解析队列（${newVideo.gameLabel}）：${resolvedTitle}`);
    setVideoUrl('');
    setVideoTitle('');
    setStageCode('');
    setCreatorName('');
    setSelectedFileName('');
  };

  const filteredVideos = videos.filter((video) => {
    const matchesGame = gameFilter === 'all' ? true : video.game === gameFilter;
    const matchesStatus =
      statusFilter === 'all' ? true : video.status === statusFilter ||
        (statusFilter === 'processing' && video.status === 'queued');
    const term = searchTerm.trim().toLowerCase();
    const matchesSearch =
      !term ||
      video.title.toLowerCase().includes(term) ||
      video.stageCode.toLowerCase().includes(term) ||
      video.creator.toLowerCase().includes(term) ||
      video.bvId.toLowerCase().includes(term) ||
      (video.gameLabel || '').toLowerCase().includes(term);
    return matchesGame && matchesStatus && matchesSearch;
  });

  return (
    <div className="space-y-8">
      {/* Page Title Strip */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 px-1">
        <div>
          <h1 className="text-2xl sm:text-[28px] font-semibold tracking-tight text-slate-950 text-balance">
            添加攻略视频
          </h1>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-600 font-mono tabular-nums">
          <span>
            已入库{' '}
            <strong className="text-slate-950 font-semibold">
              {videos.filter((v) => v.status === 'indexed').length}
            </strong>{' '}
            部
          </span>
          <span aria-hidden="true">·</span>
          <span>
            队列解析中{' '}
            <strong className="text-[#008DB3] font-semibold">
              {videos.filter((v) => v.status === 'processing').length}
            </strong>{' '}
            部
          </span>
        </div>
      </div>

      {/* Unified Single-Entry Ingestion Split */}
      <form
        onSubmit={e => e.preventDefault()}
        className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch"
      >
        {/* Left Card: Video Source Input / Dropzone (7 cols) */}
        <section className="lg:col-span-7 glass-panel-elevated rounded-2xl p-6 sm:p-7 flex flex-col justify-between">
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-slate-950">视频源导入</h2>
              <div
                className="inline-flex items-center gap-1 p-1 glass-subsurface rounded-xl"
                role="tablist"
                aria-label="视频导入方式"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={sourceMode === 'url'}
                  disabled={busy}
                  onClick={() => changeSource('url')}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer ${
                    sourceMode === 'url'
                      ? 'bg-white text-slate-950 shadow-sm'
                      : 'text-slate-600 hover:text-slate-950'
                  }`}
                >
                  <Link2 className="w-3.5 h-3.5" />
                  链接 / BV 号
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={sourceMode === 'file'}
                  disabled={busy}
                  onClick={() => changeSource('file')}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer ${
                    sourceMode === 'file'
                      ? 'bg-white text-slate-950 shadow-sm'
                      : 'text-slate-600 hover:text-slate-950'
                  }`}
                >
                  <UploadCloud className="w-3.5 h-3.5" />
                  本地视频文件
                </button>
              </div>
            </div>

            {sourceMode === 'url' ? (
              <div className="space-y-4">
                <div>
                  <label
                    htmlFor="video-url-input"
                    className="block text-xs font-medium text-slate-700 mb-1.5"
                  >
                    {DEMO_MODE ? 'B站 / YouTube 视频链接或 BV 号' : 'B 站视频链接或 BV 号'}
                  </label>
                  <input
                    id="video-url-input"
                    type="text"
                    value={videoUrl}
                    disabled={busy}
                    onChange={(e) => changeUrl(e.target.value)}
                    onKeyDown={e => {
                      if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
                      e.preventDefault();
                      void readMetadata();
                    }}
                    placeholder="https://www.bilibili.com/video/BV..."
                    className={`w-full px-4 py-2.5 rounded-xl bg-white/85 border border-slate-200/80 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-4 transition-all ${
                      isEndfieldForm
                        ? 'focus:border-[#D4B800] focus:ring-[#FFE600]/25'
                        : 'focus:border-[#17D1FF] focus:ring-[#17D1FF]/15'
                    }`}
                  />
                </div>
                {!DEMO_MODE && (
                  <div className="space-y-2 text-xs">
                    <button type="button" disabled={busy || !videoUrl.trim()} className="text-[#008DB3] disabled:opacity-40 mr-4"
                      onClick={() => void readMetadata()}>读取视频信息</button>
                    <button type="button" disabled={busy || !videoUrl.trim()} className="text-[#008DB3] disabled:opacity-40"
                      onClick={() => void runAction(async () => {
                        const result = await checkSubtitle(videoUrl.trim());
                        setFeedbackNotice(result.has_subtitle
                          ? `可获取字幕：${result.subtitle_type || '字幕'}`
                          : '未发现可用的 API 字幕（视频画面仍可能有硬字幕或攻略文字）');
                      })}>检测字幕</button>
                    <div className="flex gap-2">
                      <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="按关键词搜索 B 站"
                        onKeyDown={e => {
                          if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
                          e.preventDefault();
                          void searchCandidates();
                        }}
                        className="min-w-0 flex-1 rounded-lg bg-white/85 border border-slate-200 px-3 py-2" />
                      <button type="button" disabled={busy || !searchQuery.trim()} className="px-2 text-[#008DB3] disabled:opacity-40"
                        onClick={() => void searchCandidates()}>搜索</button>
                    </div>
                    {candidates.map(video => (
                      <button key={video.bvid} type="button" disabled={busy} className="block text-left text-slate-700 hover:text-[#008DB3]"
                        onClick={() => { setCandidates([]); void readMetadata(video.bvid); }}>
                        {video.title} · {video.author} · {video.duration}
                      </button>
                    ))}
                    {previewReady && <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white/75 p-3">
                      {preview.cover_url && <ResilientImage src={preview.cover_url.replace(/^http:/, 'https:')} alt="" className="w-24 shrink-0 aspect-video rounded object-cover" />}
                      <div className="min-w-0 space-y-1">
                        <p className="font-medium text-slate-800">已读取 · {preview.bvid}</p>
                        <p className="text-slate-500">{[
                          preview.duration_seconds ? timecode(preview.duration_seconds) : null,
                          preview.published_at ? `发布于 ${new Date(preview.published_at).toLocaleDateString('zh-CN')}` : null,
                        ].filter(Boolean).join(' · ')}</p>
                        {preview.description && <p className="line-clamp-2 break-words text-slate-600">{preview.description}</p>}
                      </div>
                    </div>}
                    <p className="rounded-lg border border-slate-200 bg-white/75 p-3 leading-relaxed text-slate-600">
                      系统自动解析全片：优先读取 API 字幕，同时按时间分段检查画面。需要发送静音画面时只确认一次。
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={DEMO_MODE ? 'video/*' : '.mp4,.mov,.mkv,.webm,.m4a,.mp3,.wav,.flac'}
                  className="hidden"
                  onChange={(e) => handleFilePicked(e.target.files?.[0])}
                />
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragging(false);
                    handleFilePicked(e.dataTransfer.files?.[0]);
                  }}
                  onClick={() => fileInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  className={`rounded-2xl border-2 border-dashed p-7 text-center transition-all cursor-pointer ${
                    isDragging
                      ? isEndfieldForm
                        ? 'border-[#F5D800] bg-[#FFE600]/14'
                        : 'border-[#17D1FF] bg-[#17D1FF]/10'
                      : 'border-slate-300/80 bg-white/50 hover:border-slate-400 hover:bg-white/80'
                  }`}
                >
                  <div
                    className={`w-11 h-11 rounded-2xl flex items-center justify-center mx-auto mb-3 ${
                      isEndfieldForm
                        ? 'bg-[#FFE600]/28 text-[#9A7400]'
                        : 'bg-[#17D1FF]/15 text-[#008DB3]'
                    }`}
                  >
                    <UploadCloud className="w-5 h-5" />
                  </div>
                  <p className="text-sm font-semibold text-slate-900">
                    {selectedFileName
                      ? `已选择文件：${selectedFileName}`
                      : '拖拽攻略录像至此，或点击选择本地视频'}
                  </p>
                  <p className="text-xs text-slate-500 mt-1 font-mono">
                    MP4 / MKV / MOV
                  </p>
                </div>
              </div>
            )}

            {/* Metadata Fields Grid */}
            <fieldset disabled={busy} className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 pt-2 border-t border-slate-200/70 disabled:opacity-50">
              <div className="sm:col-span-3">
                <label
                  htmlFor="video-title-input"
                  className="block text-xs font-medium text-slate-700 mb-1"
                >
                  攻略标题
                </label>
                <input
                  id="video-title-input"
                  type="text"
                  value={videoTitle}
                  onChange={(e) => setVideoTitle(e.target.value)}
                  placeholder={
                    isEndfieldForm
                      ? '四号谷地集成工业满产线蓝图配平思路'
                      : '14-18 磨难双快活打法思路'
                  }
                  className={`w-full px-3.5 py-2 rounded-xl bg-white/80 border border-slate-200/80 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none ${
                    isEndfieldForm ? 'focus:border-[#D4B800]' : 'focus:border-[#17D1FF]'
                  }`}
                />
              </div>
              <div>
                <label
                  htmlFor="stage-code-input"
                  className="block text-xs font-medium text-slate-700 mb-1"
                >
                  关卡 / 区域代号
                </label>
                <input
                  id="stage-code-input"
                  type="text"
                  value={stageCode}
                  onChange={(e) => setStageCode(e.target.value)}
                  placeholder={isEndfieldForm ? '如：四号谷地 AIC' : '如：H12-4'}
                  className={`w-full px-3.5 py-2 rounded-xl bg-white/80 border border-slate-200/80 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none ${
                    isEndfieldForm ? 'focus:border-[#D4B800]' : 'focus:border-[#17D1FF]'
                  }`}
                />
              </div>
              <div className="sm:col-span-2">
                <label
                  htmlFor="creator-input"
                  className="block text-xs font-medium text-slate-700 mb-1"
                >
                  攻略作者 / UP 主
                </label>
                <input
                  id="creator-input"
                  type="text"
                  value={creatorName}
                  onChange={(e) => setCreatorName(e.target.value)}
                  placeholder={
                    isEndfieldForm ? '如：塔卫二工业院 / 协议核心工坊' : '如：萧然Q / 魔法Zc目录'
                  }
                  className={`w-full px-3.5 py-2 rounded-xl bg-white/80 border border-slate-200/80 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none ${
                    isEndfieldForm ? 'focus:border-[#D4B800]' : 'focus:border-[#17D1FF]'
                  }`}
                />
              </div>
            </fieldset>
          </div>
        </section>

        {/* Right Card: Unified Game & Extraction Settings (5 cols) */}
        <section className="lg:col-span-5 glass-panel-elevated rounded-2xl p-6 sm:p-7 flex flex-col justify-between gap-6">
          <div className="space-y-5">
            <div>
              <h2 className="text-base font-semibold text-slate-950">解析配置</h2>
            </div>

            {/* Target Game Switcher inside the single ingestion form */}
            <fieldset disabled={busy || !games.length} className="space-y-2">
              <span className="block text-xs font-medium text-slate-700">
                所属作品
              </span>
              {!DEMO_MODE && <button type="button" aria-pressed={!targetGame}
                className={`rounded-lg border px-3 py-1.5 text-xs ${!targetGame ? 'bg-slate-100 border-slate-300' : 'bg-white/65 border-slate-200'}`}
                onClick={() => handleSwitchTargetGame(null)}>暂不指定</button>}
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => handleSwitchTargetGame('arknights')}
                  className={`px-3 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer border text-left flex items-center justify-between ${
                    targetGame === 'arknights'
                      ? 'bg-[#17D1FF]/16 border-[#17D1FF] text-slate-950'
                      : 'bg-white/65 border-slate-200/75 text-slate-600 hover:bg-white'
                  }`}
                >
                  <span>明日方舟</span>
                  <span
                    aria-hidden="true"
                    className="w-2.5 h-2.5 rotate-45 bg-[#17D1FF] shrink-0"
                  />
                </button>
                <button
                  type="button"
                  onClick={() => handleSwitchTargetGame('endfield')}
                  className={`px-3 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer border text-left flex items-center justify-between ${
                    targetGame === 'endfield'
                      ? 'bg-[#FFE600]/28 border-[#EAB308] text-[#18181B]'
                      : 'bg-white/65 border-slate-200/75 text-slate-600 hover:bg-white'
                  }`}
                >
                  <span>明日方舟：终末地</span>
                  <span
                    aria-hidden="true"
                    className="w-2.5 h-2.5 bg-[#FFE600] border border-[#18181B]/40 shrink-0"
                  />
                </button>
              </div>
            </fieldset>

            {/* Dynamic Category Selector per Game */}
            <fieldset disabled={busy || !games.length} className="space-y-2">
              <span className="block text-xs font-medium text-slate-700">
                归档知识分区
              </span>
              <div className="grid grid-cols-2 gap-2">
                {categoryOptions.map((opt) => {
                  const active = category === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setCategory(opt.id)}
                      className={`px-3 py-2 rounded-xl text-xs font-medium transition-all cursor-pointer border text-left ${
                        active
                          ? isEndfieldForm
                            ? 'bg-[#FFE600]/22 border-[#EAB308] text-[#18181B] font-semibold'
                            : 'bg-[#17D1FF]/14 border-[#17D1FF] text-slate-950 font-semibold'
                          : 'bg-white/65 border-slate-200/75 text-slate-600 hover:bg-white'
                      }`}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            {/* Agent Extraction Toggles */}
            <fieldset disabled={!DEMO_MODE} className="space-y-3 border-t border-slate-200/70 pt-4 disabled:opacity-50">
              <ToggleRow
                label={
                  isEndfieldForm
                    ? '工业产线与蓝图拓扑识别'
                    : '关键帧部署网格识别'
                }
                checked={extractKeyframes}
                isEndfield={isEndfieldForm}
                onChange={setExtractKeyframes}
              />
              <ToggleRow
                label={
                  isEndfieldForm
                    ? '技能连携与破韧轴切分'
                    : '语音转写与技能轴切分'
                }
                checked={extractAsr}
                isEndfield={isEndfieldForm}
                onChange={setExtractAsr}
              />
              <ToggleRow
                label={
                  isEndfieldForm
                    ? '干员与装备词库关联'
                    : '干员词库实体自动关联'
                }
                checked={linkOperators}
                isEndfield={isEndfieldForm}
                onChange={setLinkOperators}
              />
            </fieldset>
          </div>

          <div className="space-y-3">
            {catalogError && <p role="alert" className="text-xs text-rose-600">{catalogError}</p>}
            {feedbackNotice && (
              <div role={failed ? 'alert' : 'status'} className={`px-3.5 py-2.5 rounded-xl text-xs flex items-center gap-2 ${failed ? 'bg-rose-50 text-rose-700' : 'bg-[#17D1FF]/12 text-slate-800'}`}>
                {!failed && <CheckCircle2 className="w-4 h-4 text-[#008DB3] shrink-0" />}
                <span>{feedbackNotice}</span>
              </div>
            )}
            <button
              type="button"
              onClick={() => void handleSubmitIngestion()}
              disabled={busy || !games.length || (!DEMO_MODE && (sourceMode === 'url' ? !previewReady : !selectedFile))}
              className={`w-full ark-chamfer-sm py-3 px-5 inline-flex items-center justify-center gap-2 text-sm font-semibold active:scale-[0.99] transition-all cursor-pointer ${
                isEndfieldForm
                  ? 'bg-[#FFE600] text-[#18181B] hover:bg-[#F5D800] shadow-[0_8px_22px_rgba(234,179,8,0.28)]'
                  : 'bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF] shadow-[0_8px_22px_rgba(23,209,255,0.3)]'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              {sourceMode === 'url' && !DEMO_MODE ? '解析整条视频' : '解析并加入知识库'}
            </button>
          </div>
        </section>
      </form>

      {videos.map(video => video.taskId && video.visualConfirmation &&
        <VideoVisualConfirmation key={video.taskId} video={video} taskId={video.taskId}
          details={video.visualConfirmation} />)}
      {visualReports.map(video => {
        const coverage = video.visualCoverage!;
        return <section key={video.taskId} className="glass-panel rounded-xl p-4 space-y-2" aria-label="全片解析进度">
          <p className="text-sm font-semibold">{video.title}</p>
          <p className="text-xs text-slate-700">{video.progressStage}</p>
          <p className="text-xs text-slate-500">已尝试 {coverage.processed}/{coverage.total} 段 · 有证据 {coverage.with_evidence} 段 · 无证据 {coverage.empty} 段 · 失败 {coverage.failed.length} 段</p>
          <VisualWindows windows={coverage.failed} />
        </section>;
      })}

      {/* Bottom Section: Unified Video Archive (Compact Cards + List View) */}
      <section className="space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Game Filter */}
            <div className="inline-flex items-center gap-1 p-1 glass-subsurface rounded-xl w-fit">
              {(
                [
                  { id: 'all', label: '全部作品' },
                  { id: 'arknights', label: '明日方舟' },
                  { id: 'endfield', label: '终末地' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setGameFilter(tab.id)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer ${
                    gameFilter === tab.id
                      ? tab.id === 'endfield'
                        ? 'bg-[#FFE600] text-[#18181B] font-semibold shadow-sm'
                        : tab.id === 'arknights'
                        ? 'bg-[#17D1FF] text-[#071B26] font-semibold shadow-sm'
                        : 'bg-white text-slate-950 font-semibold shadow-sm'
                      : 'text-slate-600 hover:text-slate-950'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Status Filter */}
            <div className="flex items-center gap-1 p-1 glass-subsurface rounded-xl w-fit">
              {(
                [
                  { id: 'all', label: '全部状态' },
                  { id: 'processing', label: '解析队列中' },
                  { id: 'indexed', label: '已完成入库' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setStatusFilter(tab.id)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer ${
                    statusFilter === tab.id
                      ? 'bg-white text-slate-950 shadow-sm'
                      : 'text-slate-600 hover:text-slate-950'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="relative flex-1 sm:w-64">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="搜索关卡、BV号或作者…"
                className="w-full pl-8 pr-3 py-1.5 rounded-xl glass-panel text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[#17D1FF]"
                aria-label="筛选已导入视频"
              />
            </div>

            {/* Card / List View Switcher */}
            <div
              className="inline-flex items-center gap-1 p-1 glass-subsurface rounded-xl shrink-0"
              role="group"
              aria-label="视图切换"
            >
              <button
                type="button"
                onClick={() => setViewMode('card')}
                aria-label="卡片视角"
                aria-pressed={viewMode === 'card'}
                className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer ${
                  viewMode === 'card'
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-600 hover:text-slate-950'
                }`}
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                卡片
              </button>
              <button
                type="button"
                onClick={() => setViewMode('list')}
                aria-label="列表视角"
                aria-pressed={viewMode === 'list'}
                className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer ${
                  viewMode === 'list'
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-600 hover:text-slate-950'
                }`}
              >
                <List className="w-3.5 h-3.5" />
                列表
              </button>
            </div>
          </div>
        </div>

        {filteredVideos.length === 0 ? (
          <div className="glass-panel rounded-2xl p-10 text-center space-y-2">
            <Film className="w-6 h-6 text-slate-400 mx-auto" />
            <p className="text-sm font-medium text-slate-800">暂无符合条件的视频记录</p>
          </div>
        ) : viewMode === 'card' ? (
          /* Compact 4-column Card Grid */
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredVideos.map((video) => {
              const isProcessing = video.status === 'processing' || video.status === 'queued';
              const isEndfield = video.game === 'endfield';
              const accentText = isEndfield ? 'text-[#9A7400]' : 'text-[#008DB3]';
              return (
                <article
                  key={video.id}
                  className="glass-panel rounded-xl overflow-hidden flex flex-col justify-between hover:shadow-[0_12px_28px_rgba(15,23,42,0.08)] transition-all duration-200 relative"
                >
                  <div>
                    <div className="relative h-32 bg-slate-100 overflow-hidden">
                      <ResilientImage
                        src={video.thumbnail}
                        alt={video.title}
                        className="w-full h-full object-cover"
                        fallbackLabel={video.stageCode}
                      />
                      <div
                        aria-hidden="true"
                        className={`absolute top-0 left-0 right-0 h-[2.5px] ${
                          isEndfield ? 'bg-[#FFE600]' : 'bg-[#17D1FF]'
                        }`}
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-slate-950/75 via-slate-950/15 to-transparent" />
                      <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between text-[11px] text-white font-mono tabular-nums">
                        <span
                          className={`font-semibold ${
                            isEndfield ? 'text-[#FFE600]' : 'text-cyan-200'
                          }`}
                        >
                          {video.stageCode}
                        </span>
                        <span>{video.duration}</span>
                      </div>
                    </div>

                    <div className="p-3.5 space-y-2">
                      <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500 font-mono tabular-nums">
                        <span className="truncate">
                          <span className={`font-semibold ${accentText}`}>
                            {video.gameLabel}
                          </span>
                          {' · '}
                          {video.creator}
                        </span>
                        <span className="shrink-0">{video.publishedAt || (video.indexedAt && `入库 ${video.indexedAt}`)}</span>
                      </div>

                      <h3 className="text-[13px] font-semibold text-slate-950 leading-snug line-clamp-2 min-h-[36px]">
                        {video.title}
                      </h3>

                      {isProcessing && (
                        <div className="space-y-1.5 pt-0.5">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-[#008DB3] font-medium truncate pr-2">
                              {video.paused ? '已暂停' : video.pauseRequested ? '等待暂停…' : video.progressStage || '解析中'}
                            </span>
                            <span className="font-mono tabular-nums text-slate-700 font-semibold">
                              {video.progress}%
                            </span>
                          </div>
                          <div className="h-1 w-full rounded-full bg-slate-200/80 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                isEndfield ? 'bg-[#FFE600]' : 'bg-[#17D1FF]'
                              }`}
                              style={{ width: `${video.progress}%` }}
                            />
                          </div>
                        </div>
                      )}
                      {video.status === 'error' && (
                        <p role="alert" className="text-xs text-rose-700 line-clamp-2">{video.progressStage}</p>
                      )}
                      {video.status === 'draft' && <p className="text-xs text-slate-500">档案已保存，尚未完成入库</p>}
                    </div>
                  </div>

                  {/* Card Footer Actions */}
                  <div className="px-3.5 py-2.5 border-t border-slate-200/65 flex items-center justify-between gap-2 text-[11px]">
                    <span className="font-mono tabular-nums text-slate-500 truncate">
                      {video.categoryLabel} · {video.chunkCount} 切片
                    </span>
                    <div className="flex items-center gap-2.5 shrink-0">
                      {isProcessing && video.taskId && (
                        <button type="button" disabled={busy} className="text-[#008DB3]"
                          onClick={() => void runAction(() => onPauseTask(video.taskId!, !video.pauseRequested))}>
                          {video.pauseRequested ? '继续' : '暂停'}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onInspectVideo(video.id)}
                        className="font-medium text-slate-700 hover:text-slate-950 transition-colors cursor-pointer whitespace-nowrap"
                      >
                        详情
                      </button>
                      <button
                        type="button"
                        onClick={() => onAskAboutVideo(video)}
              disabled={video.backend && video.status !== "indexed"}
                        className={`inline-flex items-center gap-1 font-semibold hover:text-slate-950 transition-colors cursor-pointer whitespace-nowrap ${accentText}`}
                      >
                        <MessageSquareText className="w-3 h-3" />
                        提问
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          /* Compact List View */
          <div className="glass-panel rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-200/75 text-xs text-slate-500 font-medium bg-white/40">
                    <th className="py-3 pl-5 pr-3 font-medium whitespace-nowrap">视频</th>
                    <th className="py-3 px-3 font-medium whitespace-nowrap">作品 / 关卡</th>
                    <th className="py-3 px-3 font-medium whitespace-nowrap">状态 / 切片</th>
                    <th className="py-3 pl-3 pr-5 font-medium text-right whitespace-nowrap">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200/60 text-xs">
                  {filteredVideos.map((video) => {
                    const isProcessing = video.status === 'processing' || video.status === 'queued';
                    const isEndfield = video.game === 'endfield';
                    const accentText = isEndfield ? 'text-[#9A7400]' : 'text-[#008DB3]';
                    return (
                      <tr
                        key={video.id}
                        className="hover:bg-white/60 transition-colors duration-150"
                      >
                        <td className="py-2.5 pl-5 pr-3 min-w-[280px]">
                          <div className="flex items-center gap-3">
                            <div className="w-20 aspect-video rounded-lg overflow-hidden bg-slate-100 shrink-0 relative">
                              <ResilientImage
                                src={video.thumbnail}
                                alt={video.title}
                                className="w-full h-full object-cover"
                                fallbackLabel={video.stageCode}
                              />
                              <span
                                aria-hidden="true"
                                className={`absolute top-0 left-0 right-0 h-[2px] ${
                                  isEndfield ? 'bg-[#FFE600]' : 'bg-[#17D1FF]'
                                }`}
                              />
                            </div>
                            <div className="min-w-0">
                              <button
                                type="button"
                                onClick={() => onInspectVideo(video.id)}
                                className={`text-left text-[13px] font-semibold text-slate-900 transition-colors line-clamp-1 cursor-pointer ${
                                  isEndfield ? 'hover:text-[#9A7400]' : 'hover:text-[#008DB3]'
                                }`}
                              >
                                {video.title}
                              </button>
                              <div className="text-[11px] text-slate-500 font-mono tabular-nums mt-0.5">
                                {[video.creator, video.publishedAt || (video.indexedAt && `入库 ${video.indexedAt}`), video.bvId, video.duration].filter(Boolean).join(' · ')}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="py-2.5 px-3 whitespace-nowrap">
                          <div className={`font-mono font-semibold ${accentText}`}>
                            {video.stageCode}
                          </div>
                          <div className="text-[11px] text-slate-500 mt-0.5">
                            {video.gameLabel} · {video.categoryLabel}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 min-w-[160px]">
                          {isProcessing ? (
                            <div className="space-y-1 max-w-[180px]">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="text-[#008DB3] font-medium truncate pr-2">
                                  {video.paused ? '已暂停' : video.pauseRequested ? '等待暂停…' : video.progressStage || '解析中'}
                                </span>
                                <span className="font-mono tabular-nums font-semibold text-slate-700">
                                  {video.progress}%
                                </span>
                              </div>
                              <div className="h-1 w-full rounded-full bg-slate-200/80 overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    isEndfield ? 'bg-[#FFE600]' : 'bg-[#17D1FF]'
                                  }`}
                                  style={{ width: `${video.progress}%` }}
                                />
                              </div>
                            </div>
                          ) : video.status === 'draft' ? (
                            <span className="text-slate-500">尚未完成入库</span>
                          ) : video.status === 'error' ? (
                            <span role="alert" className="text-rose-700">{video.progressStage || '导入失败'}</span>
                          ) : (
                            <span className="font-mono tabular-nums text-slate-600">
                              已入库 · {video.chunkCount} 切片{!video.backend && ` · ${video.keyframeCount} 帧`}
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 pl-3 pr-5 text-right whitespace-nowrap">
                          <div className="inline-flex items-center gap-3">
                            {isProcessing && video.taskId && (
                              <button type="button" disabled={busy} className="text-[#008DB3]"
                                onClick={() => void runAction(() => onPauseTask(video.taskId!, !video.pauseRequested))}>
                                {video.pauseRequested ? '继续' : '暂停'}
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => onInspectVideo(video.id)}
                              className="font-medium text-slate-700 hover:text-slate-950 cursor-pointer"
                            >
                              详情
                            </button>
                            <button
                              type="button"
                              onClick={() => onAskAboutVideo(video)}
              disabled={video.backend && video.status !== "indexed"}
                              className={`inline-flex items-center gap-1 font-semibold hover:text-slate-950 cursor-pointer ${accentText}`}
                            >
                              <MessageSquareText className="w-3.5 h-3.5" />
                              提问
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

interface ToggleRowProps {
  label: string;
  checked: boolean;
  isEndfield?: boolean;
  onChange: (next: boolean) => void;
}

function ToggleRow({ label, checked, isEndfield, onChange }: ToggleRowProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <p className="text-xs sm:text-[13px] font-medium text-slate-900">{label}</p>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={`relative w-10 h-5.5 rounded-full transition-colors duration-150 shrink-0 cursor-pointer ${
          checked
            ? isEndfield
              ? 'bg-[#FFE600]'
              : 'bg-[#17D1FF]'
            : 'bg-slate-300/80'
        }`}
      >
        <span
          className={`block w-4 h-4 rounded-full shadow-sm transition-transform duration-150 ${
            checked ? 'translate-x-5' : 'translate-x-1'
          } ${checked && isEndfield ? 'bg-[#18181B]' : 'bg-white'}`}
        />
      </button>
    </div>
  );
}
