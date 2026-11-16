import { useEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Clock,
  Compass,
  Cpu,
  MessageSquarePlus,
  MessageSquareText,
  PlayCircle,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { QA_SCENARIOS } from '../data/mockStrategyData';
import {
  KnowledgeCategory,
  QaScenario,
  RetrievedChunk,
  StrategyVideo,
} from '../types/strategy';
import { ResilientImage } from './ResilientImage';
import { streamAsk, type AudioConfirmation, type ExternalSearchDetails } from '../api/qa';
import { DEMO_MODE, presentCitation } from '../data/backendPresentation';
import type { AgentStep as BackendStep, AudioImportOption, Citation, Conversation, ExternalVideo, GameState } from '../types/backend';
import { renderMarkdown } from '../utils/markdown';
import { AudioChoice, ExternalCandidates, PauseAudio, TranscriptOffer } from './LiveTurnControls';

interface QaWorkspacePageProps {
  videos: StrategyVideo[];
  scopedVideo: StrategyVideo | null;
  onClearScopedVideo: () => void;
  onInspectVideo: (videoId: string, timestamp?: string) => void;
  onSaveTranscript: (video: AudioImportOption) => Promise<string | undefined>;
  transcriptTasks: Record<string, StrategyVideo | undefined>;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  scenario?: QaScenario;
  citations?: Citation[];
  steps?: BackendStep[];
  candidates?: ExternalVideo[];
  searchDetails?: ExternalSearchDetails;
  importOffers?: AudioImportOption[];
  confirmation?: AudioConfirmation;
  audioSelection?: string[];
  taskId?: string;
  paused?: boolean;
  pending?: boolean;
  agentModeUsed?: boolean;
  error?: string;
}

interface ChatThread {
  id: string;
  title: string;
  categoryLabel: string;
  updatedAt: string;
  messages: ChatMessage[];
  gameState?: GameState;
  agentEnabled?: boolean;
}

const SCOPE_OPTIONS: { id: KnowledgeCategory; label: string }[] = [
  { id: 'all', label: '全部库' },
  { id: 'main', label: '主线活动' },
  { id: 'roguelike', label: '集成战略' },
  { id: 'cc', label: '危机合约' },
  { id: 'operator', label: '干员测评' },
];

const STARTER_PROMPTS = [
  { ...QA_SCENARIOS[0], tag: '关卡打法' },
  { ...QA_SCENARIOS[1], tag: '集成战略' },
  { id: 'starter-15-16', prompt: '15-16 磨难险地平民低配通关轴怎么摆？', tag: '可补查 B 站' },
];

const INITIAL_THREADS: ChatThread[] = QA_SCENARIOS.map((scenario, idx) => ({
  id: `thread-${scenario.id}`,
  title:
    idx === 0
      ? '14-21 磨难双核挂机摆完轴'
      : idx === 1
      ? '萨米 N15 双王结局抓位与藏品'
      : '维什戴尔 X 模组性价比分析',
  categoryLabel:
    scenario.category === 'main'
      ? '主线活动'
      : scenario.category === 'roguelike'
      ? '集成战略'
      : '干员测评',
  updatedAt: idx === 0 ? '刚刚' : idx === 1 ? '12 分钟前' : '昨天',
  messages: [
    {
      id: `msg-u-${scenario.id}`,
      role: 'user',
      content: scenario.prompt,
      timestamp: '00:36',
    },
    {
      id: `msg-a-${scenario.id}`,
      role: 'assistant',
      content: scenario.tacticalSummary,
      timestamp: '00:36',
      scenario,
    },
  ],
}));

const CHAT_KEY = 'prts-live-chat-v1';
const STAGE_LABELS: Record<string, string> = {
  game_state: '对局状态', knowledge_search: '本地知识库', answer_check: '片段核验',
  answer: '整理回答', answer_review: '答案复核', bilibili_search: 'B 站搜索',
  external_subtitles: '临时字幕检索', external_answer: '综合回答', external_review: '综合复核',
  external_audio_1: '候选 1 下载与转写', external_audio_2: '候选 2 下载与转写',
  external_audio_reuse: '复用已转写音轨',
};
const STATUS_LABELS = { running: '进行中', completed: '完成', warning: '提示', failed: '失败' };

function newThread(): ChatThread {
  return { id: crypto.randomUUID(), title: '新战术对话', categoryLabel: '全部库', updatedAt: '刚刚', messages: [] };
}

function restoreChat(): { threads: ChatThread[]; activeId: string } {
  if (DEMO_MODE) return { threads: INITIAL_THREADS, activeId: INITIAL_THREADS[0].id };
  try {
    const saved = JSON.parse(localStorage.getItem(CHAT_KEY) || 'null');
    if (saved?.threads?.length) {
      return {
        threads: saved.threads.map((t: ChatThread) => ({
          ...t, messages: t.messages.map(m => m.pending
            ? { ...m, pending: false, confirmation: undefined, error: '刷新前的回答未完成，可以重新提问。' }
            : m),
        })),
        activeId: saved.activeId,
      };
    }
    const legacy: { conversations?: Conversation[]; activeId?: string } =
      JSON.parse(localStorage.getItem('video-rag-conversations') || '{}');
    if (legacy.conversations?.length) {
      const threads = [...legacy.conversations].sort((a, b) => (b.createdAt ?? b.updatedAt) - (a.createdAt ?? a.updatedAt))
        .map(t => ({
          id: t.id, title: t.title, categoryLabel: '全部库', updatedAt: new Date(t.updatedAt).toLocaleDateString('zh-CN'),
          gameState: t.gameState,
          messages: t.messages.map((m): ChatMessage => ({
            id: `legacy-${m.id}`, role: m.role === 'q' ? 'user' : 'assistant', content: m.text,
            timestamp: '', citations: m.citations, steps: m.agentSteps, candidates: m.externalVideos,
            importOffers: m.audioImportOptions, error: m.streaming ? '旧版的回答未完成，可以重新提问。' : m.error,
          })),
        }));
      return { threads, activeId: threads.some(t => t.id === legacy.activeId) ? legacy.activeId! : threads[0].id };
    }
  } catch { /* 忽略无效本地历史 */ }
  const thread = newThread();
  return { threads: [thread], activeId: thread.id };
}

function highlightExcerpt(excerpt: string, terms: string[]) {
  if (!terms.length) return excerpt;
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const regex = new RegExp(`(${escaped.join('|')})`, 'g');
  const parts = excerpt.split(regex);
  return parts.map((part, idx) => {
    if (terms.includes(part)) {
      return (
        <mark
          key={`${part}-${idx}`}
          className="bg-[#17D1FF]/22 text-slate-950 font-medium px-1 rounded"
        >
          {part}
        </mark>
      );
    }
    return <span key={`${part}-${idx}`}>{part}</span>;
  });
}

export function QaWorkspacePage({
  videos,
  scopedVideo,
  onClearScopedVideo,
  onInspectVideo,
  onSaveTranscript,
  transcriptTasks,
}: QaWorkspacePageProps) {
  const [initial] = useState(restoreChat);
  const [threads, setThreads] = useState(initial.threads);
  const [activeThreadId, setActiveThreadId] = useState(initial.activeId);
  const [selectedScope, setSelectedScope] = useState<KnowledgeCategory>('all');
  const [gameScope, setGameScope] = useState<'all' | 'arknights' | 'endfield'>('all');
  const isEndfieldComposer = gameScope === 'endfield';
  const [inputValue, setInputValue] = useState<string>('');
  const [expandedTraceMsgIds, setExpandedTraceMsgIds] = useState<Record<string, boolean>>({});
  const [highlightedChunkId, setHighlightedChunkId] = useState<string | null>(null);
  const [demoThinking, setDemoThinking] = useState<boolean>(false);
  const requests = useRef(new Map<string, AbortController>());
  const scopedRequest = useRef<StrategyVideo>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const activeThread = threads.find((t) => t.id === activeThreadId) ?? null;
  const isThinking = DEMO_MODE ? demoThinking : !!activeThread?.messages.some(m => m.pending);
  const agentMode = !!(activeThread?.agentEnabled ?? activeThread?.gameState);

  useEffect(() => {
    if (DEMO_MODE) return;
    try { localStorage.setItem(CHAT_KEY, JSON.stringify({ threads, activeId: activeThreadId })); }
    catch { /* 不影响当前会话 */ }
  }, [threads, activeThreadId]);

  useEffect(() => () => requests.current.forEach(request => request.abort()), []);

  useEffect(() => {
    if (scopedVideo && scopedRequest.current !== scopedVideo) {
      scopedRequest.current = scopedVideo;
      if (DEMO_MODE) setSelectedScope(scopedVideo.category);
      const newThreadId = crypto.randomUUID();
      const subject = scopedVideo.stageCode || scopedVideo.title;
      const blankThread: ChatThread = {
        id: newThreadId,
        title: `${subject} 定向追问`,
        categoryLabel: scopedVideo.categoryLabel,
        updatedAt: '刚刚',
        messages: [],
      };
      setThreads((prev) => [blankThread, ...prev]);
      setActiveThreadId(newThreadId);
      setInputValue(`请结合「${subject}」视频攻略，说明开局部署顺位和关键技能轴`);
      textareaRef.current?.focus();
    } else if (!scopedVideo) scopedRequest.current = null;
  }, [scopedVideo]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [activeThread?.messages.length, isThinking]);

  const handleNewChat = () => {
    const thread = newThread();
    setThreads((prev) => [thread, ...prev]);
    setActiveThreadId(thread.id);
    onClearScopedVideo();
    setInputValue('');
    textareaRef.current?.focus();
  };

  const handleDeleteThread = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    requests.current.get(id)?.abort();
    const fallback = threads.find(t => t.id !== id) ?? newThread();
    if (activeThreadId === id) {
      setActiveThreadId(fallback.id);
      onClearScopedVideo();
      setInputValue('');
    }
    setThreads(prev => {
      const remaining = prev.filter(t => t.id !== id);
      return remaining.length ? remaining : [fallback];
    });
  };

  const selectThread = (id: string) => {
    if (id !== activeThreadId && !DEMO_MODE) {
      onClearScopedVideo();
      setInputValue('');
    }
    setActiveThreadId(id);
  };

  const updateMessage = (threadId: string, msgId: string, update: (message: ChatMessage) => Partial<ChatMessage>) => {
    setThreads(prev => prev.map(t => t.id !== threadId ? t : ({
      ...t, messages: t.messages.map(m => m.id === msgId ? { ...m, ...update(m) } : m),
    })));
  };

  const matchScenarioForQuestion = (question: string): QaScenario => {
    const lower = question.toLowerCase();
    const matched =
      QA_SCENARIOS.find(
        (s) =>
          (lower.includes('萨米') || lower.includes('肉鸽') || lower.includes('n15')) &&
          s.id === 'scenario-sami-n15'
      ) ||
      QA_SCENARIOS.find(
        (s) =>
          (lower.includes('模组') || lower.includes('红蒂') || lower.includes('性价比')) &&
          s.id === 'scenario-wisadel-mod'
      ) ||
      QA_SCENARIOS.find(
        (s) =>
          (lower.includes('14-21') || lower.includes('挂机') || lower.includes('玛恩纳')) &&
          s.id === 'scenario-14-21'
      );

    if (matched) return matched;

    const base =
      selectedScope === 'roguelike'
        ? QA_SCENARIOS[1]
        : selectedScope === 'operator'
        ? QA_SCENARIOS[2]
        : QA_SCENARIOS[0];

    return {
      ...base,
      id: `custom-${Date.now()}`,
      prompt: question,
      headline: scopedVideo
        ? `${scopedVideo.stageCode} · 视频切片解析结论`
        : `${question.slice(0, 22)}${question.length > 22 ? '…' : ''} · 战术解答`,
      tacticalSummary: scopedVideo
        ? `基于视频《${scopedVideo.title}》（${scopedVideo.creator}）共 ${scopedVideo.chunkCount} 个语义切片的分析结果：建议按先锋反隐开局、高台核心控场、地面决战技兜底的节奏落位，注意保留费用应对中盘精英波次。`
        : base.tacticalSummary,
    };
  };

  const sendQuestion = (questionText: string) => {
    const trimmed = questionText.trim();
    if (!trimmed || isThinking || !activeThread || requests.current.has(activeThread.id)) return;

    const nowLabel = new Date().toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });

    const userMsg: ChatMessage = {
      id: `msg-u-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: nowLabel,
    };

    const currentThreadId = activeThread.id;
    const shouldRename = activeThread.messages.length === 0;
    const assistantId = `msg-a-${crypto.randomUUID()}`;
    const assistant: ChatMessage = {
      id: assistantId, role: 'assistant', timestamp: nowLabel, content: '', pending: true, agentModeUsed: agentMode,
    };

    setThreads((prev) =>
      prev.map((t) =>
        t.id === currentThreadId
          ? {
              ...t,
              title: shouldRename
                ? trimmed.slice(0, 18) + (trimmed.length > 18 ? '…' : '')
                : t.title,
              updatedAt: '刚刚',
              messages: DEMO_MODE ? [...t.messages, userMsg] : [...t.messages, userMsg, assistant],
            }
          : t
      )
    );
    setInputValue('');
    if (!DEMO_MODE) {
      const controller = new AbortController();
      requests.current.set(currentThreadId, controller);
      const patch = (update: (message: ChatMessage) => Partial<ChatMessage>) => updateMessage(currentThreadId, assistantId, update);
      const history = activeThread.messages.filter(m => m.content && !m.error && !m.pending).slice(-8)
        .map(({ role, content }) => ({ role, content }));
      const requestQuestion = gameScope === 'all' ? trimmed
        : `关于${gameScope === 'endfield' ? '明日方舟：终末地' : '明日方舟'}：${trimmed}`;
      void streamAsk(requestQuestion, {
        onTask: taskId => patch(() => ({ taskId })),
        onGameState: gameState => setThreads(prev => prev.map(t => t.id === currentThreadId ? { ...t, gameState } : t)),
        onPauseState: paused => patch(m => m.paused === paused ? {} : ({ paused })),
        onAudioConfirmation: confirmation => patch(() => ({
          confirmation, audioSelection: confirmation.videos.map(video => video.bvid),
        })),
        onAudioImportOffer: importOffers => patch(() => ({ importOffers })),
        onCitations: citations => patch(() => ({ citations })),
        onDelta: text => patch(m => ({ content: m.content + text })),
        onAnswerReplace: (content, citations) => patch(() => ({ content, citations })),
        onExternalSearch: (candidates, searchDetails) => patch(() => ({ candidates, searchDetails })),
        onAgentStep: step => patch(m => {
          const steps = [...(m.steps || [])];
          const i = steps.findIndex(s => s.stage === step.stage);
          if (i < 0) steps.push(step); else steps[i] = step;
          return { steps, ...(step.stage.startsWith('external_audio_') && step.stage !== 'external_audio_reuse'
            ? { confirmation: undefined } : {}) };
        }),
        onDone: citations => patch(() => ({ citations, pending: false, confirmation: undefined })),
      }, history, agentMode ? activeThread.gameState ?? {} : undefined, controller.signal).catch(err => {
        if (!controller.signal.aborted) patch(() => ({
          pending: false, confirmation: undefined, error: err instanceof Error ? err.message : '问答失败',
        }));
      }).finally(() => requests.current.delete(currentThreadId));
      return;
    }
    setDemoThinking(true);

    window.setTimeout(() => {
      const scenario = matchScenarioForQuestion(trimmed);
      const assistantMsg: ChatMessage = {
        id: `msg-a-${Date.now()}`,
        role: 'assistant',
        content: scenario.tacticalSummary,
        timestamp: nowLabel,
        scenario,
        agentModeUsed: agentMode,
      };
      setThreads((prev) =>
        prev.map((t) =>
          t.id === currentThreadId
            ? {
                ...t,
                updatedAt: '刚刚',
                messages: [...t.messages, assistantMsg],
              }
            : t
        )
      );
      setDemoThinking(false);
    }, 550);
  };

  const handleComposerSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendQuestion(inputValue);
  };

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      sendQuestion(inputValue);
    }
  };

  const toggleTrace = (msgId: string) => {
    setExpandedTraceMsgIds((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  const handleCitationJump = (msgId: string, citationIndex: number, chunks: RetrievedChunk[]) => {
    const target = chunks.find((c) => c.citationIndex === citationIndex);
    if (!target) return;
    const domId = `source-${msgId}-${target.id}`;
    setHighlightedChunkId(domId);
    const el = document.getElementById(domId);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  const indexedCount = videos.filter((v) => v.status === 'indexed').length;
  const totalChunks = videos.reduce((sum, v) => sum + v.chunkCount, 0);

  return (
    <div className="flex flex-col lg:flex-row gap-5 lg:h-[calc(100vh-132px)] lg:min-h-[640px]">
      {/* Left Sidebar: Chat History & Knowledge Context */}
      <aside className="lg:w-[272px] shrink-0 glass-panel rounded-2xl p-4 flex flex-col justify-between gap-4">
        <div className="space-y-4 min-h-0 flex flex-col flex-1">
          <button
            type="button"
            onClick={handleNewChat}
            className="w-full ark-chamfer-sm py-2.5 px-4 inline-flex items-center justify-center gap-2 text-[13px] font-semibold bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF] active:scale-[0.99] transition-all cursor-pointer shadow-[0_6px_18px_rgba(23,209,255,0.28)]"
          >
            <MessageSquarePlus className="w-4 h-4" />
            新建战术问答
          </button>

          <div className="space-y-1.5 overflow-y-auto pr-0.5 flex-1">
            <div className="px-2 py-1 text-xs font-medium text-slate-500">
              最近对话
            </div>
            {threads.map((thread) => {
              const isActive = thread.id === activeThreadId;
              return (
                <div
                  key={thread.id}
                  onClick={() => selectThread(thread.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      selectThread(thread.id);
                    }
                  }}
                  className={`group w-full px-3 py-2.5 rounded-xl text-left transition-all cursor-pointer flex items-start justify-between gap-2 ${
                    isActive
                      ? 'bg-white/95 shadow-sm border border-[#17D1FF]/45'
                      : 'hover:bg-white/55 border border-transparent'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-[13px] truncate ${
                        isActive ? 'font-semibold text-slate-950' : 'font-medium text-slate-700'
                      }`}
                    >
                      {thread.title}
                    </p>
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-0.5 font-mono tabular-nums">
                      <span>{thread.categoryLabel}</span>
                      <span aria-hidden="true">·</span>
                      <span>{thread.updatedAt}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    aria-label={`删除对话 ${thread.title}`}
                    onClick={(e) => handleDeleteThread(thread.id, e)}
                    className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-all cursor-pointer shrink-0"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Clean Unboxed Knowledge Base Summary */}
        <div className="pt-3 border-t border-slate-200/70 px-1 space-y-1 text-xs text-slate-500">
          <div className="font-medium text-slate-800">当前挂载知识库</div>
          <div className="font-mono tabular-nums">
            {indexedCount} 部攻略视频 · {totalChunks} 语义切片
          </div>
        </div>
      </aside>

      {/* Main Conversational AI Q&A Panel */}
      <section className="flex-1 min-w-0 glass-panel-elevated rounded-2xl flex flex-col overflow-hidden relative">
        {/* Top Precision Accent Hairline */}
        <div
          aria-hidden="true"
          className="absolute top-0 left-10 right-10 h-[2px] bg-gradient-to-r from-transparent via-[#17D1FF] to-transparent opacity-80 z-10"
        />

        {/* Chat Header Bar */}
        <div className="px-5 sm:px-7 py-3.5 border-b border-slate-200/70 bg-white/45 flex flex-wrap items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <MessageSquareText className="w-4 h-4 text-[#008DB3] shrink-0" />
            <h1 className="text-sm font-semibold text-slate-950 truncate">
              {activeThread?.title || 'PRTS 战术问答'}
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex gap-1 rounded-xl glass-subsurface p-1" aria-label="游戏主题">
              {(['all', 'arknights', 'endfield'] as const).map(game => (
                <button key={game} type="button" aria-pressed={gameScope === game}
                  title="为问题补充游戏主题，仍检索整个知识库"
                  onClick={() => { setGameScope(game); setSelectedScope('all'); }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${gameScope === game
                    ? game === 'endfield' ? 'bg-[#FFE600] text-[#18181B]' : game === 'arknights' ? 'bg-[#17D1FF] text-[#071B26]' : 'bg-white text-slate-950'
                    : 'text-slate-500 hover:text-slate-950'}`}>
                  {game === 'all' ? '全部' : game === 'endfield' ? '终末地' : '明日方舟'}
                </button>
              ))}
            </div>
          <div
            className="flex flex-wrap items-center gap-1 p-0.5 glass-subsurface rounded-lg"
            role="tablist"
            aria-label="检索范围"
          >
            {(isEndfieldComposer ? [
              { id: 'all' as const, label: '全部库' }, { id: 'aic' as const, label: '工业产线' },
              { id: 'exploration' as const, label: '探索 Boss' }, { id: 'combo' as const, label: '配队连携' },
              { id: 'char' as const, label: '角色评测' },
            ] : SCOPE_OPTIONS).map((opt) => {
              const active = selectedScope === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  disabled={!DEMO_MODE && opt.id !== 'all'}
                  title={!DEMO_MODE && opt.id !== 'all' ? '后端暂未支持分区检索' : undefined}
                  onClick={() => setSelectedScope(opt.id)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap cursor-pointer ${
                    active
                      ? 'bg-white text-slate-950 shadow-sm'
                      : 'text-slate-600 hover:text-slate-950 disabled:opacity-40 disabled:cursor-not-allowed'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          </div>
        </div>

        {/* Scrollable Conversation Thread */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-7">
          {!activeThread || activeThread.messages.length === 0 ? (
            /* Clean Mainstream AI Welcome / Empty Chat State */
            <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center py-8 space-y-7">
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-[#17D1FF]/15 border border-[#17D1FF]/40 flex items-center justify-center mx-auto">
                  <Sparkles className="w-5 h-5 text-[#008DB3]" />
                </div>
                <h2 className="text-2xl font-semibold text-slate-950 tracking-tight text-balance">
                  有什么战术、工业或探索问题？
                </h2>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full text-left">
                {[
                  { ...QA_SCENARIOS[0], tag: '明日方舟' },
                  { ...QA_SCENARIOS[1], tag: '终末地 · 工业产线' },
                  { ...QA_SCENARIOS[2], tag: '终末地 · 探索 Boss' },
                  { id: 'endfield-wuling', prompt: '武陵城集成工业枢纽怎么扩建息壤产线与供电网？', tag: '可补查 B 站' },
                ].map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => sendQuestion(preset.prompt)}
                    className="p-4 rounded-2xl bg-white/75 hover:bg-white border border-slate-200/80 hover:border-[#17D1FF]/70 transition-all cursor-pointer flex flex-col justify-between gap-3 shadow-sm"
                  >
                    <span className="text-[13px] font-medium text-slate-900 leading-snug line-clamp-3">
                      {preset.prompt}
                    </span>
                    <span className="flex items-center justify-between gap-2 w-full text-xs">
                      <span className="font-medium text-[#008DB3] inline-flex items-center gap-1">
                        直接提问 <ChevronRight className="w-3.5 h-3.5" />
                      </span>
                      <span className="text-[11px] text-slate-500">{preset.tag}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Conversational Message Stream */
            <div className="max-w-4xl mx-auto space-y-7">
              {activeThread.messages.map((msg) => {
                if (msg.role === 'user') {
                  return (
                    <div key={msg.id} className="flex justify-end">
                      <div className="max-w-[85%] sm:max-w-[72%] px-4 py-3 rounded-2xl rounded-tr-sm bg-[#17D1FF]/16 border border-[#17D1FF]/40 text-slate-950 text-[14px] sm:text-[15px] leading-relaxed shadow-sm">
                        {msg.content}
                      </div>
                    </div>
                  );
                }

                const scenario = msg.scenario;
                const isTraceExpanded = !!expandedTraceMsgIds[msg.id];
                const sourceChunks = scenario?.retrievedChunks ?? (msg.citations || []).map((cite, idx) =>
                  presentCitation(cite, idx, msg.candidates?.find(video => video.bvid === cite.video_id)));
                const liveSteps: import('../types/strategy').AgentStep[] = (msg.steps || []).map(step => ({
                  id: step.stage, label: STAGE_LABELS[step.stage] || step.stage, findings: step.message,
                  durationText: STATUS_LABELS[step.status] || step.status, detail: '',
                }));
                const steps = scenario?.agentSteps ?? liveSteps;
                const markup = !scenario ? renderMarkdown(msg.content.replace(/\[引用([0-9]{1,6})\]/g, (ref, n) => {
                  const chunk = sourceChunks[Number(n) - 1];
                  return chunk ? `[来源 ${n}](#source-${msg.id}-${chunk.id})` : ref;
                })) : '';

                return (
                  <div key={msg.id} className="flex items-start gap-3.5">
                    {/* Assistant Emblem */}
                    <div className="w-8 h-8 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center justify-center shrink-0 mt-0.5">
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 28 28"
                        fill="none"
                        aria-hidden="true"
                      >
                        <polygon
                          points="14,3 25,14 14,25 3,14"
                          stroke="#0F172A"
                          strokeWidth="2"
                          fill="#FFFFFF"
                        />
                        <polygon points="14,9 19,14 14,19 9,14" fill="#17D1FF" />
                      </svg>
                    </div>

                    {/* Assistant Response Body */}
                    <div className="flex-1 min-w-0 space-y-4">
                      {msg.agentModeUsed && (
                        <span className="inline-flex items-center gap-1.5 rounded-lg bg-[#17D1FF]/15 px-2.5 py-1.5 text-xs font-semibold text-[#007894]">
                          <Compass className="w-3.5 h-3.5" /> 战术推演
                        </span>
                      )}
                      {/* Inline Collapsible Agent Trace */}
                      {steps.length > 0 && (
                        <div>
                          <button
                            type="button"
                            onClick={() => toggleTrace(msg.id)}
                            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/75 hover:bg-white border border-slate-200/80 text-xs text-slate-700 transition-colors cursor-pointer"
                          >
                            <Cpu className="w-3.5 h-3.5 text-[#008DB3]" />
                            <span className="font-medium">
                              {msg.pending ? '执行中' : '已结束'} · {steps.length} 步 Agent 检索与校验
                            </span>
                            <span className="text-slate-400">·</span>
                            <span className="text-[#008DB3] font-mono tabular-nums">
                              引用 {sourceChunks.length} 段切片
                            </span>
                            <ChevronDown
                              className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-150 ${
                                isTraceExpanded ? 'rotate-180' : ''
                              }`}
                            />
                          </button>

                          {isTraceExpanded && (
                            <div className="mt-2.5 p-4 rounded-xl bg-white/70 border border-slate-200/75 space-y-2.5">
                              {steps.map((step, idx) => (
                                <div
                                  key={step.id}
                                  className="flex items-start justify-between gap-4 text-xs"
                                >
                                  <div className="flex items-start gap-2.5 min-w-0">
                                    <span className="font-mono tabular-nums text-[#008DB3] font-semibold shrink-0">
                                      0{idx + 1}
                                    </span>
                                    <div>
                                      <span className="font-semibold text-slate-900">
                                        {step.label}
                                      </span>
                                      {step.toolName && <span className="ml-2 font-mono text-[#008DB3]">{step.toolName}</span>}
                                      <span className="text-slate-500 ml-2">
                                        {step.findings}
                                      </span>
                                    </div>
                                  </div>
                                  <span className="font-mono tabular-nums text-slate-400 shrink-0">
                                    {step.durationText}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Main Answer Prose & Structured Strategy Content */}
                      <div className="glass-panel rounded-2xl p-5 sm:p-6 space-y-5">
                        {scenario ? (
                          <>
                            <div className="space-y-2.5">
                              <h3 className="text-base sm:text-lg font-semibold text-slate-950 tracking-tight">
                                {scenario.headline}
                              </h3>
                              <p className="text-[14px] sm:text-[15px] leading-relaxed text-slate-700">
                                {scenario.tacticalSummary}
                              </p>
                            </div>

                            <ul className="space-y-2 text-[13px] sm:text-sm text-slate-700 border-t border-slate-200/70 pt-4">
                              {scenario.keyTakeaways.map((point) => (
                                <li
                                  key={point}
                                  className="flex items-start gap-2.5 leading-relaxed"
                                >
                                  <span
                                    aria-hidden="true"
                                    className="mt-1.5 w-1.5 h-1.5 rotate-45 bg-[#17D1FF] shrink-0"
                                  />
                                  <span>{point}</span>
                                </li>
                              ))}
                            </ul>

                            {/* Compact Deployment Sequence Table */}
                            <div className="border-t border-slate-200/70 pt-4 space-y-2.5">
                              <div className="flex items-center justify-between text-xs">
                                <span className="font-semibold text-slate-900">
                                  推荐部署顺位与技能轴
                                </span>
                              </div>
                              <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse">
                                  <thead>
                                    <tr className="border-b border-slate-200/80 text-[11px] text-slate-500">
                                      <th className="py-2 pr-2 font-medium">顺位</th>
                                      <th className="py-2 px-2 font-medium">时间点</th>
                                      <th className="py-2 px-2 font-medium">干员与操作</th>
                                      <th className="py-2 px-2 font-medium">朝向</th>
                                      <th className="py-2 pl-2 font-medium text-right">引用</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-200/55 text-xs">
                                    {scenario.deploymentTimeline.map((row) => (
                                      <tr key={`${row.order}-${row.operator}`}>
                                        <td className="py-2.5 pr-2 font-mono tabular-nums text-slate-400 align-top">
                                          {row.order}
                                        </td>
                                        <td className="py-2.5 px-2 font-mono tabular-nums text-[#008DB3] font-semibold align-top whitespace-nowrap">
                                          {row.timestamp}
                                        </td>
                                        <td className="py-2.5 px-2 align-top">
                                          <span className="font-semibold text-slate-900">
                                            {row.operator}
                                          </span>
                                          <span className="text-slate-500 ml-1.5">
                                            ({row.skill})
                                          </span>
                                          <p className="text-slate-600 mt-0.5 leading-relaxed">
                                            {row.note}
                                          </p>
                                        </td>
                                        <td className="py-2.5 px-2 text-slate-700 align-top whitespace-nowrap">
                                          {row.direction}
                                        </td>
                                        <td className="py-2.5 pl-2 text-right align-top whitespace-nowrap">
                                          <button
                                            type="button"
                                            onClick={() =>
                                              handleCitationJump(
                                                msg.id,
                                                row.citationIndex,
                                                scenario.retrievedChunks
                                              )
                                            }
                                            className="font-mono tabular-nums font-semibold text-[#008DB3] hover:text-slate-950 cursor-pointer"
                                          >
                                            [{row.citationIndex}]
                                          </button>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>

                            {/* Compact Operators Row */}
                            <div className="border-t border-slate-200/70 pt-4">
                              <div className="text-xs font-semibold text-slate-900 mb-2.5">
                                核心配置干员
                              </div>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                                {scenario.recommendedOperators.map((op) => (
                                  <div
                                    key={op.name}
                                    className="px-3.5 py-2.5 rounded-xl bg-white/75"
                                  >
                                    <div className="flex items-baseline justify-between gap-2 text-xs">
                                      <span className="font-semibold text-slate-950">
                                        {op.name}
                                      </span>
                                      <span className="text-[#008DB3] font-medium">
                                        {op.moduleNote}
                                      </span>
                                    </div>
                                    <p className="text-[11px] text-slate-500 mt-0.5">
                                      {op.profession} · {op.skillLabel}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            </div>
                            {/* Tactical Planning Extended Analysis Block */}
                            {msg.agentModeUsed && scenario.agentAnalysis && (
                              <div className="border-t border-slate-200/70 pt-4 space-y-3">
                                <div className="flex items-center gap-2 text-xs font-semibold text-slate-950">
                                  <Compass className="w-3.5 h-3.5 text-[#008DB3]" />
                                  <span>通关推演与破局建议</span>
                                </div>

                                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600 font-mono">
                                  {scenario.agentAnalysis.toolsUsed.map((tool) => (
                                    <span key={tool.name}>
                                      <strong className="text-[#008DB3] font-medium">
                                        {tool.name}
                                      </strong>
                                      ：{tool.summary}
                                    </span>
                                  ))}
                                </div>

                                <p className="text-xs leading-relaxed text-slate-700 bg-[#17D1FF]/10 rounded-xl px-3.5 py-2.5">
                                  {scenario.agentAnalysis.crossCheckInsight}
                                </p>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                                  {scenario.agentAnalysis.alternativeSubstitutions.map(
                                    (sub) => (
                                      <div
                                        key={sub.target}
                                        className="px-3.5 py-2.5 rounded-xl bg-white/75 text-xs"
                                      >
                                        <div className="font-medium text-slate-900">
                                          {sub.target} →{' '}
                                          <span className="text-[#008DB3]">
                                            {sub.replacement}
                                          </span>
                                        </div>
                                        <div className="text-[11px] text-slate-500 mt-0.5">
                                          {sub.condition}
                                        </div>
                                      </div>
                                    )
                                  )}
                                </div>
                              </div>
                            )}
                          </>
                        ) : (
                          <>
                            {msg.content && <div className="prts-answer text-sm leading-relaxed text-slate-700 break-words"
                              dangerouslySetInnerHTML={{ __html: markup }} />}
                            {msg.pending && <p role="status" className="text-xs text-slate-500">
                              {msg.confirmation ? '等待选择是否转写音轨…' : (msg.steps || []).at(-1)?.message || '正在提交问题…'}
                            </p>}
                            {msg.error && <p role="alert" className="text-sm text-rose-700">{msg.error}</p>}
                          </>
                        )}
                      </div>

                      {/* Grounded Video Source Cards Strip inside AI Reply (Perplexity / Kimi style) */}
                      {sourceChunks.length > 0 && (
                        <div className="space-y-2.5">
                          <div className="text-xs font-medium text-slate-500">
                            参考攻略视频切片 ({sourceChunks.length})
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {sourceChunks.map((chunk) => {
                              const domId = `source-${msg.id}-${chunk.id}`;
                              const isHighlighted = highlightedChunkId === domId;
                              return (
                                <button
                                  key={chunk.id}
                                  id={domId}
                                  type="button"
                                  onClick={() => chunk.sourceUrl
                                    ? window.open(chunk.sourceUrl, '_blank', 'noopener,noreferrer')
                                    : onInspectVideo(chunk.videoId, chunk.jumpTimestamp)}
                                  className={`text-left glass-panel rounded-xl p-3 flex items-start gap-3 transition-all cursor-pointer hover:bg-white/95 ${
                                    isHighlighted
                                      ? 'ring-2 ring-[#17D1FF] bg-white'
                                      : ''
                                  }`}
                                >
                                  <div className="relative w-24 aspect-video rounded-lg overflow-hidden bg-slate-100 shrink-0">
                                    <ResilientImage
                                      src={chunk.thumbnail}
                                      alt={chunk.videoTitle}
                                      className="w-full h-full object-cover"
                                      fallbackLabel={chunk.stageCode}
                                    />
                                    <div className="absolute inset-0 bg-gradient-to-t from-slate-950/75 via-transparent to-transparent" />
                                    <span className="absolute bottom-1 left-1.5 text-[10px] font-mono tabular-nums text-white font-semibold">
                                      {chunk.jumpTimestamp}
                                    </span>
                                  </div>

                                  <div className="min-w-0 flex-1 space-y-1">
                                    <div className="flex items-center justify-between gap-2 text-[11px] font-mono tabular-nums">
                                      <span className="text-[#008DB3] font-semibold truncate">
                                        [{chunk.citationIndex}] {chunk.creator}{chunk.publishedAt && ` · ${chunk.publishedAt}`}
                                      </span>
                                      <span className="text-slate-400">
                                        {chunk.similarityScore == null ? chunk.timestampRange : `${chunk.similarityScore}% 匹配`}
                                      </span>
                                    </div>
                                    <p className="text-xs font-medium text-slate-900 line-clamp-1">
                                      {chunk.videoTitle}
                                    </p>
                                    <p className="text-[11px] text-slate-600 line-clamp-2 leading-relaxed">
                                      {highlightExcerpt(chunk.excerpt, chunk.matchedTerms)}
                                    </p>
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      {msg.candidates && !(msg.pending && msg.confirmation) &&
                        <ExternalCandidates videos={msg.candidates} details={msg.searchDetails} pending={msg.pending} />}
                      {msg.pending && msg.taskId && msg.confirmation && (
                        <AudioChoice taskId={msg.taskId} confirmation={msg.confirmation}
                          candidates={msg.candidates} details={msg.searchDetails}
                          selected={msg.audioSelection ?? []}
                          onToggle={bvid => updateMessage(activeThreadId, msg.id, current => {
                            const chosen = current.audioSelection ?? [];
                            return { audioSelection: chosen.includes(bvid)
                              ? chosen.filter(id => id !== bvid) : [...chosen, bvid] };
                          })}
                          onDecision={() => updateMessage(activeThreadId, msg.id, () => ({ confirmation: undefined }))} />
                      )}
                      {msg.pending && msg.taskId && (msg.steps || []).filter(step =>
                        /^external_audio_[12]$/.test(step.stage) && step.status === 'running').map(step =>
                        <PauseAudio key={step.stage} taskId={msg.taskId!} paused={!!msg.paused} message={step.message} />)}
                      {!!msg.importOffers?.length &&
                        <TranscriptOffer videos={msg.importOffers} tasks={transcriptTasks} onSave={onSaveTranscript} />}
                    </div>
                  </div>
                );
              })}

              {DEMO_MODE && isThinking && (
                <div className="flex items-start gap-3.5">
                  <div className="w-8 h-8 rounded-xl bg-white border border-slate-200/80 shadow-sm flex items-center justify-center shrink-0">
                    <Sparkles className="w-4 h-4 text-[#008DB3]" />
                  </div>
                  <div className="glass-panel rounded-2xl px-4 py-3 text-xs text-slate-600 flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-[#008DB3]" />
                    <span>正在检索攻略视频关键帧与语音转写切片…</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Bottom-Docked Unified Chat Input Composer */}
        <div className="px-4 sm:px-8 py-4 border-t border-slate-200/70 bg-white/70 backdrop-blur-xl shrink-0">
          <form onSubmit={handleComposerSubmit} className="max-w-4xl mx-auto space-y-2.5">
            {scopedVideo && (
              <div className="px-3 py-1.5 rounded-lg bg-[#17D1FF]/12 border border-[#17D1FF]/35 flex items-center justify-between gap-3 text-xs">
                <span className="text-slate-800 truncate flex items-center gap-1.5">
                  <PlayCircle className="w-3.5 h-3.5 text-[#008DB3] shrink-0" />
                  {DEMO_MODE ? '定向追问视频' : '问题参考视频（仍检索全库）'}：<strong className="font-semibold">{scopedVideo.title}</strong>
                </span>
                <button
                  type="button"
                  onClick={onClearScopedVideo}
                  aria-label="清除参考视频"
                  className="text-slate-500 hover:text-slate-950 cursor-pointer shrink-0"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <div className={`flex flex-col gap-2 p-2.5 rounded-2xl bg-white/95 border border-slate-200/90 focus-within:ring-4 transition-all shadow-sm ${isEndfieldComposer
              ? 'focus-within:border-[#EAB308] focus-within:ring-[#FFE600]/20' : 'focus-within:border-[#17D1FF] focus-within:ring-[#17D1FF]/15'}`}>
              <textarea
                ref={textareaRef}
                rows={1}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleTextareaKeyDown}
                placeholder="输入关卡、干员或配队问题…"
                className="w-full resize-none max-h-32 px-2 py-1 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none leading-relaxed"
                aria-label="输入战术问题"
              />
              <div className="flex items-center justify-between gap-3 pt-1 px-1">
                <button type="button" role="switch" aria-checked={agentMode} disabled={isThinking || !activeThread}
                  title={activeThread?.gameState?.turn ? `当前回合：${activeThread.gameState.turn}` : '开启对局 Agent，根据回合、资源与可选动作给出建议'}
                  onClick={() => setThreads(prev => prev.map(t => t.id === activeThreadId
                    ? { ...t, agentEnabled: !agentMode } : t))}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium transition-all cursor-pointer border disabled:opacity-50 ${agentMode
                    ? isEndfieldComposer ? 'bg-[#FFE600]/26 border-[#EAB308] text-[#18181B] font-semibold' : 'bg-[#17D1FF]/16 border-[#17D1FF]/60 text-slate-950 font-semibold'
                    : 'bg-slate-100/80 border-slate-200/80 text-slate-600 hover:text-slate-950'}`}>
                  <Compass className={`w-3.5 h-3.5 ${agentMode ? 'text-[#008DB3]' : 'text-slate-500'}`} />
                  <span>战术推演</span>
                  <span aria-hidden="true" className={`w-7 h-4 rounded-full transition-colors flex items-center px-0.5 ${agentMode ? 'bg-[#17D1FF]' : 'bg-slate-300'}`}>
                    <span className={`w-3 h-3 rounded-full bg-white shadow-sm transition-transform ${agentMode ? 'translate-x-3' : 'translate-x-0'}`} />
                  </span>
                </button>
              <button
                type="submit"
                disabled={!inputValue.trim() || isThinking}
                aria-label="发送问题"
                className={`ark-chamfer-sm h-8 px-4 inline-flex items-center justify-center gap-1.5 text-xs font-semibold disabled:opacity-45 disabled:cursor-not-allowed transition-all cursor-pointer shrink-0 ${isEndfieldComposer ? 'bg-[#FFE600] text-[#18181B] hover:bg-[#F5D800]' : 'bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF]'}`}
              >
                <span>发送</span>
                <ArrowUp className="w-3.5 h-3.5" />
              </button>
              </div>
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}
