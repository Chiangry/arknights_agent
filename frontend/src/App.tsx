import { useEffect, useState } from 'react';
import { KnowledgeLibraryPage } from './components/KnowledgeLibraryPage';
import { QaWorkspacePage } from './components/QaWorkspacePage';
import { TopNav } from './components/TopNav';
import { VideoIngestPage } from './components/VideoIngestPage';
import { VideoPreviewModal } from './components/VideoPreviewModal';
import { BACKDROP_IMAGE, INITIAL_VIDEOS } from './data/mockStrategyData';
import { PageView, StrategyVideo } from './types/strategy';
import { DEMO_MODE } from './data/backendPresentation';
import { useVideoTasks } from './hooks/useVideoTasks';

export default function App() {
  const [activePage, setActivePage] = useState<PageView>('qa');
  const [demoVideos, setDemoVideos] = useState<StrategyVideo[]>(INITIAL_VIDEOS);
  const backend = useVideoTasks(!DEMO_MODE);
  const videos = DEMO_MODE ? demoVideos : backend.library;
  const [scopedVideo, setScopedVideo] = useState<StrategyVideo | null>(null);
  const [modalState, setModalState] = useState<{
    videoId: string;
    timestamp?: string;
  } | null>(null);

  // Smooth simulated progression for processing videos in the queue
  useEffect(() => {
    if (!DEMO_MODE) return;
    const hasProcessing = demoVideos.some((v) => v.status === 'processing');
    if (!hasProcessing) return;

    const timer = window.setInterval(() => {
      setDemoVideos((prev) =>
        prev.map((video) => {
          if (video.status !== 'processing') return video;
          const nextProgress = Math.min(100, video.progress + 9);
          if (nextProgress >= 100) {
            return {
              ...video,
              status: 'indexed',
              progress: 100,
              progressStage: '向量入库完成',
            };
          }
          return {
            ...video,
            progress: nextProgress,
            progressStage:
              nextProgress > 65
                ? '正在写入多模态向量索引'
                : '正在执行语音转写与站位关键帧对齐',
          };
        })
      );
    }, 1800);

    return () => window.clearInterval(timer);
  }, [demoVideos]);

  const handleAddVideo = (newVideo: StrategyVideo) => {
    setDemoVideos((prev) => [newVideo, ...prev]);
  };

  const handleInspectVideo = (videoId: string, timestamp?: string) => {
    setModalState({ videoId, timestamp });
  };

  const handleAskAboutVideo = (video: StrategyVideo) => {
    setModalState(null);
    setScopedVideo(video);
    setActivePage('qa');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const inspectedVideo = modalState
    ? [...videos, ...backend.queue].find((v) => v.id === modalState.videoId) ?? null
    : null;

  return (
    <div className="min-h-screen relative bg-[#F3F6FA] text-slate-900 selection:bg-[#17D1FF]/30 selection:text-slate-950">
      {/* Subtle Atmospheric Rhodes + Endfield Light-Mode Backdrop + Tactical Grid */}
      <div
        aria-hidden="true"
        className="fixed inset-0 pointer-events-none overflow-hidden z-0"
      >
        <img
          src={BACKDROP_IMAGE}
          alt=""
          className="w-full h-full object-cover opacity-[0.14] scale-105"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-[#F5F7FA]/75 via-[#F3F6FA]/82 to-[#EFF3F8]/95" />
        <div className="absolute inset-0 tactical-grid-bg opacity-70" />
        <div className="absolute -top-32 right-[10%] w-[540px] h-[540px] rounded-full bg-[#17D1FF]/14 blur-[120px]" />
        <div className="absolute bottom-[-130px] left-[8%] w-[500px] h-[500px] rounded-full bg-[#FFE600]/14 blur-[125px]" />
      </div>

      {/* Main Foreground Shell */}
      <div className="relative z-10 flex flex-col min-h-screen">
        <TopNav activePage={activePage} onNavigate={setActivePage} />

        <main
          className={`flex-1 w-full px-4 sm:px-6 lg:px-8 pt-4 ${
            activePage === 'qa' ? 'pb-4' : 'pb-14'
          }`}
        >
<div className="w-full max-w-[1600px] mx-auto">
          {backend.error && (
            <p role="alert" className="glass-panel mb-3 rounded-xl p-3 text-xs text-rose-700">
              知识库加载失败：{backend.error}{' '}
              <button type="button" className="underline" onClick={() => void backend.refresh()}>重试</button>
            </p>
          )}
          <div hidden={activePage !== 'qa'}>
            <QaWorkspacePage
              videos={videos}
              scopedVideo={scopedVideo}
              onClearScopedVideo={() => setScopedVideo(null)}
              onInspectVideo={handleInspectVideo}
              onSaveTranscript={backend.saveTranscript}
              transcriptTasks={backend.transcriptTasks}
            />
          </div>

          <div hidden={activePage !== 'ingest'}>
            <VideoIngestPage
              videos={DEMO_MODE ? videos : [...backend.queue, ...videos]}
              onAddVideo={handleAddVideo}
              onTrackTask={backend.track}
              onPauseTask={backend.pause}
              onInspectVideo={(id) => handleInspectVideo(id)}
              onAskAboutVideo={handleAskAboutVideo}
            />
          </div>

          {activePage === 'library' && (
            <KnowledgeLibraryPage
              videos={videos}
              onInspectVideo={(id) => handleInspectVideo(id)}
              onAskAboutVideo={handleAskAboutVideo}
              onGoToIngest={() => setActivePage('ingest')}
            />
          )}
</div>
        </main>

        {activePage !== 'qa' && (
          <footer className="w-full px-4 sm:px-6 lg:px-8">
            <div className="w-full max-w-[1600px] mx-auto py-6 border-t border-slate-200/60 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500">
              <span>PRTS 战术攻略知识库</span>
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => setActivePage('qa')}
                  className="hover:text-slate-900 transition-colors cursor-pointer"
                >
                  AI 战术问答
                </button>
                <button
                  type="button"
                  onClick={() => setActivePage('ingest')}
                  className="hover:text-slate-900 transition-colors cursor-pointer"
                >
                  添加攻略视频
                </button>
                <button
                  type="button"
                  onClick={() => setActivePage('library')}
                  className="hover:text-slate-900 transition-colors cursor-pointer"
                >
                  攻略切片库
                </button>
              </div>
            </div>
          </footer>
        )}
      </div>

      {/* Video Keyframe & Transcript Preview Modal */}
      <VideoPreviewModal
        video={inspectedVideo}
        highlightTimestamp={modalState?.timestamp}
        onClose={() => setModalState(null)}
        onAskAboutVideo={handleAskAboutVideo}
      />
    </div>
  );
}
