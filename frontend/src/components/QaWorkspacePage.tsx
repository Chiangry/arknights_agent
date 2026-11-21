import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  ArrowDown,
  ChevronDown,
  ChevronRight,
  Clock,
  Compass,
  Cpu,
  Globe,
  MessageSquarePlus,
  MessageSquareText,
  Pencil,
  PlayCircle,
  Sparkles,
  Trash2,
  X,
  type LucideIcon,
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
import { createChatThread, deleteChatThread, getChatThread, listChatThreads, patchChatThread,
  type StoredThread, type ThreadPatch } from '../api/chat';
import { biliUrl, DEMO_MODE, presentCitation } from '../data/backendPresentation';
import type { AgentStep as BackendStep, AudioImportOption, Citation, ExternalVideo, GameState } from '../types/backend';
import { renderMarkdown } from '../utils/markdown';
import { AudioChoice, ExternalCandidates, PauseAudio, TranscriptOffer } from './LiveTurnControls';
import { useCatalog } from '../hooks/useCatalog';

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
  activityAt?: number;
  draft?: boolean;
  loaded?: boolean;
  messages: ChatMessage[];
  gameState?: GameState;
  agentEnabled?: boolean;
  gameScope?: 'all' | 'arknights' | 'endfield';
  categoryScope?: KnowledgeCategory;
  videoScope?: { id: string; title: string };
}

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

const STAGE_LABELS: Record<string, string> = {
  search_route: '搜索范围',
  game_state: '对局状态', video_lookup: '视频来源定位', knowledge_search: '本地知识库', answer_check: '片段核验',
  answer: '整理回答', answer_review: '答案复核', bilibili_search: 'B 站搜索',
  external_subtitles: '临时字幕检索', external_answer: '综合回答', external_review: '综合复核',
  external_audio_1: '候选 1 下载与转写', external_audio_2: '候选 2 下载与转写',
  external_audio_reuse: '复用已转写音轨',
};
const STATUS_LABELS = { running: '进行中', completed: '完成', warning: '提示', failed: '失败' };

function ComposerSwitch({ checked, disabled, endfield, icon: Icon, label, title, onClick }: {
  checked: boolean;
  disabled?: boolean;
  endfield: boolean;
  icon: LucideIcon;
  label: string;
  title: string;
  onClick: () => void;
}) {
  return (
    <button type="button" role="switch" aria-checked={checked} disabled={disabled} title={title} onClick={onClick}
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium transition-all cursor-pointer border disabled:opacity-50 ${checked
        ? endfield ? 'bg-[#FFE600]/26 border-[#EAB308] text-[#18181B] font-semibold' : 'bg-[#17D1FF]/16 border-[#17D1FF]/60 text-slate-950 font-semibold'
        : 'bg-slate-100/80 border-slate-200/80 text-slate-600 hover:text-slate-950'}`}>
      <Icon aria-hidden="true" className={`w-3.5 h-3.5 ${checked ? 'text-[#008DB3]' : 'text-slate-500'}`} />
      <span>{label}</span>
      <span aria-hidden="true" className={`w-7 h-4 rounded-full transition-colors flex items-center px-0.5 ${checked ? 'bg-[#17D1FF]' : 'bg-slate-300'}`}>
        <span className={`w-3 h-3 rounded-full bg-white shadow-sm transition-transform ${checked ? 'translate-x-3' : 'translate-x-0'}`} />
      </span>
    </button>
  );
}

function newThread(): ChatThread {
  return { id: crypto.randomUUID(), title: '新战术对话', categoryLabel: '全部库',
    updatedAt: '刚刚', activityAt: Date.now(), loaded: true, draft: !DEMO_MODE, messages: [] };
}

function presentThread(t: StoredThread): ChatThread {
  const activityAt = Date.parse(t.last_message_at || t.created_at);
  const videoId = t.scope.video_ids?.[0];
  return {
    id: t.id, title: t.title, activityAt, updatedAt: new Date(activityAt).toLocaleDateString('zh-CN'),
    categoryLabel: videoId ? '视频追问' : '知识库',
    gameScope: (t.scope.game_id || 'all') as ChatThread['gameScope'],
    categoryScope: (t.scope.category_id || 'all') as KnowledgeCategory,
    videoScope: videoId ? { id: videoId, title: t.scoped_video_title || videoId } : undefined,
    agentEnabled: t.agent_enabled,
    gameState: t.game_state ?? undefined,
    loaded: !!t.messages,
    messages: (t.messages ?? []).map(m => ({
      id: String(m.id), content: m.content, role: m.role,
      timestamp: new Date(m.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      pending: m.status === 'running', error: m.error ?? undefined, agentModeUsed: m.agent_mode,
      steps: m.steps, citations: m.citations,
    })),
  };
}

function threadScope(t: ChatThread) {
  return { game_id: !t.gameScope || t.gameScope === 'all' ? null : t.gameScope,
    category_id: !t.categoryScope || t.categoryScope === 'all' ? null : t.categoryScope,
    video_ids: t.videoScope ? [t.videoScope.id] : [] };
}

export function QaWorkspacePage({
  videos,
  scopedVideo,
  onClearScopedVideo,
  onInspectVideo,
  onSaveTranscript,
  transcriptTasks,
}: QaWorkspacePageProps) {
  const { games } = useCatalog();
  const [threads, setThreads] = useState<ChatThread[]>(DEMO_MODE ? INITIAL_THREADS : []);
  const [activeThreadId, setActiveThreadId] = useState(DEMO_MODE ? INITIAL_THREADS[0].id : '');
  const [historyLoading, setHistoryLoading] = useState(!DEMO_MODE);
  const [historyError, setHistoryError] = useState('');
  const [inputValue, setInputValue] = useState<string>('');
  const [webSearch, setWebSearch] = useState(false);
  const [expandedTraceMsgIds, setExpandedTraceMsgIds] = useState<Record<string, boolean>>({});
  const [demoThinking, setDemoThinking] = useState<boolean>(false);
  const requests = useRef(new Map<string, AbortController>());
  const writes = useRef(new Map<string, Promise<void>>());
  const created = useRef(new Set<string>());
  const scopedRequest = useRef<StrategyVideo>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollContentRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const jumpOnSend = useRef<string | null>(null);
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const activeThread = threads.find((t) => t.id === activeThreadId) ?? null;
  const selectedScope = activeThread?.categoryScope || 'all';
  const gameScope = activeThread?.gameScope || 'all';
  const limitedVideo = activeThread?.videoScope;
  const isEndfieldComposer = gameScope === 'endfield';
  const isThinking = DEMO_MODE ? demoThinking : !!activeThread?.messages.some(m => m.pending);
  const agentMode = !!(activeThread?.agentEnabled ?? activeThread?.gameState);

  useEffect(() => {
    if (DEMO_MODE) return;
    let ignore = false;
    void listChatThreads().then(rows => {
      if (ignore) return;
      rows.forEach(t => created.current.add(t.id));
      const restored = rows.length ? rows.map(presentThread) : [newThread()];
      setThreads(restored);
      setActiveThreadId(restored[0].id);
    }).catch(() => { if (!ignore) setHistoryError('读取历史对话失败，请刷新后重试。'); })
      .finally(() => { if (!ignore) setHistoryLoading(false); });
    return () => { ignore = true; };
  }, []);

  const serverRunning = !!activeThread?.messages.some(m => m.pending) && !requests.current.has(activeThreadId);
  const shouldLoad = activeThread?.loaded === false || serverRunning;
  useEffect(() => {
    if (DEMO_MODE || !activeThreadId || !shouldLoad) return;
    let ignore = false;
    let retry: number | undefined;
    const read = async () => {
      try {
        const thread = presentThread(await getChatThread(activeThreadId));
        if (ignore || requests.current.has(activeThreadId)) return;
        setThreads(prev => prev.map(t => t.id === activeThreadId ? thread : t));
        setHistoryError(error => error === '读取该会话失败，正在重试。' ? '' : error);
        if (thread.messages.some(m => m.pending)) retry = window.setTimeout(read, 2000);
      } catch {
        if (!ignore) {
          setHistoryError('读取该会话失败，正在重试。');
          retry = window.setTimeout(read, 4000);
        }
      }
    };
    void read();
    return () => { ignore = true; window.clearTimeout(retry); };
  }, [activeThreadId, shouldLoad]);

  useEffect(() => () => requests.current.forEach(request => request.abort()), []);

  const saveThread = (thread: ChatThread, changes?: ThreadPatch) => {
    const previous = writes.current.get(thread.id);
    const next = (previous ?? Promise.resolve()).catch(() => {}).then(async () => {
      if (!created.current.has(thread.id)) {
        await createChatThread(thread.id, { title: thread.title, scope: threadScope(thread),
          scoped_video_title: thread.videoScope?.title ?? null });
        created.current.add(thread.id);
        setThreads(prev => prev.map(t => t.id === thread.id ? { ...t, draft: false } : t));
      }
      if (changes) await patchChatThread(thread.id, changes);
    });
    writes.current.set(thread.id, next);
    return next;
  };

  const changeThread = (thread: ChatThread, local: Partial<ChatThread>, changes: ThreadPatch) => {
    const updated = { ...thread, ...local };
    setThreads(prev => prev.map(t => t.id === thread.id ? { ...t, ...local } : t));
    if (!DEMO_MODE) void saveThread(updated, changes).catch(() => {
      setHistoryError('会话设置保存失败，请刷新后重试。');
    });
  };
  const updateScope = (local: Partial<ChatThread>) => {
    if (!activeThread?.loaded && !DEMO_MODE) return;
    if (!activeThread) return;
    const updated = { ...activeThread, ...local };
    changeThread(activeThread, local, { scope: threadScope(updated), scoped_video_title: updated.videoScope?.title ?? null });
  };

  useEffect(() => {
    if (historyLoading) return;
    if (scopedVideo && scopedRequest.current !== scopedVideo) {
      scopedRequest.current = scopedVideo;
      const newThreadId = crypto.randomUUID();
      const subject = scopedVideo.stageCode || scopedVideo.title;
      const blankThread: ChatThread = {
        ...newThread(),
        id: newThreadId,
        title: `${subject} 定向追问`,
        videoScope: { id: scopedVideo.id, title: scopedVideo.title },
        categoryLabel: scopedVideo.categoryLabel,
        updatedAt: '刚刚',
        messages: [],
      };
      setThreads((prev) => [blankThread, ...prev]);
      setActiveThreadId(newThreadId);
      if (!DEMO_MODE) void saveThread(blankThread).catch(() => setHistoryError('创建会话失败，请重试。'));
      setInputValue(`请结合「${subject}」视频攻略，说明开局部署顺位和关键技能轴`);
      textareaRef.current?.focus();
    } else if (!scopedVideo) scopedRequest.current = null;
  }, [scopedVideo, historyLoading]);

  const atBottom = (el: HTMLDivElement) => el.scrollHeight - el.clientHeight - el.scrollTop <= 4;

  const jumpToBottom = () => {
    followLatest.current = true;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    setAwayFromBottom(false);
  };

  useLayoutEffect(() => {
    jumpToBottom();
    const el = scrollRef.current;
    const content = scrollContentRef.current;
    if (!el || !content) return;
    const observer = new ResizeObserver(() => {
      if (followLatest.current) el.scrollTop = el.scrollHeight;
      setAwayFromBottom(!atBottom(el));
    });
    // 流式正文、图片、检索步骤和输入框都可能改变可滚动范围。
    observer.observe(content);
    observer.observe(el);
    return () => observer.disconnect();
  }, [activeThreadId]);

  useLayoutEffect(() => {
    if (jumpOnSend.current !== activeThreadId) return;
    jumpOnSend.current = null;
    jumpToBottom();
  }, [activeThreadId, activeThread?.messages.length]);

  const handleNewChat = () => {
    const thread = newThread();
    setThreads((prev) => [thread, ...prev]);
    setActiveThreadId(thread.id);
    setHistoryError('');
    if (!DEMO_MODE) void saveThread(thread).catch(() => setHistoryError('创建会话失败，请重试。'));
    onClearScopedVideo();
    setInputValue('');
    textareaRef.current?.focus();
  };

  const handleDeleteThread = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!DEMO_MODE && !window.confirm('删除这条会话及所有消息？此操作不可撤销。')) return;
    try {
      await writes.current.get(id)?.catch(() => {});
      if (!DEMO_MODE && created.current.has(id)) await deleteChatThread(id);
    } catch {
      setHistoryError('删除会话失败，请重试。');
      return;
    }
    requests.current.get(id)?.abort();
    writes.current.delete(id);
    created.current.delete(id);
    const fallback = [...threads].sort((a, b) => (b.activityAt ?? 0) - (a.activityAt ?? 0))
      .find(t => t.id !== id) ?? newThread();
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
      if (!requests.current.has(id) && created.current.has(id)) {
        setThreads(prev => prev.map(t => t.id === id ? { ...t, loaded: false } : t));
      }
    }
    setActiveThreadId(id);
  };

  const renameThread = (thread: ChatThread, e: React.MouseEvent) => {
    e.stopPropagation();
    const title = window.prompt('新的会话标题', thread.title)?.trim().slice(0, 350);
    if (title && title !== thread.title) changeThread(thread, { title }, { title });
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
    if (!trimmed || isThinking || !activeThread || (!DEMO_MODE && !activeThread.loaded)
        || requests.current.has(activeThread.id)) return;

    jumpOnSend.current = activeThread.id;

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
    const shouldRename = activeThread.messages.length === 0 && activeThread.title === '新战术对话';
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
              activityAt: Date.now(),
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
      const requestId = crypto.randomUUID();
      void (async () => {
        await (writes.current.get(currentThreadId) ?? (created.current.has(currentThreadId)
          ? Promise.resolve() : saveThread(activeThread)));
        await streamAsk(trimmed, {
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
        }, controller.signal, { thread_id: currentThreadId, request_id: requestId, web_search: webSearch });
      })().catch(async err => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : '问答失败';
        const stored = await getChatThread(currentThreadId).catch(() => null);
        if (controller.signal.aborted) return;
        requests.current.delete(currentThreadId);
        if (stored?.messages?.some(m => m.request_id === requestId) || stored?.messages?.some(m => m.status === 'running')) {
          const thread = presentThread(stored);
          setThreads(prev => prev.map(t => t.id === currentThreadId ? thread : t));
        } else patch(() => ({ pending: false, confirmation: undefined, error: message }));
      }).finally(() => {
        if (requests.current.get(currentThreadId) === controller) requests.current.delete(currentThreadId);
      });
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

  const openCitation = (citationIndex: number, chunks: RetrievedChunk[]) => {
    const target = chunks.find((c) => c.citationIndex === citationIndex);
    if (!target) return;
    if (target.sourceUrl) window.open(target.sourceUrl, '_blank', 'noopener,noreferrer');
    else if (target.videoId) onInspectVideo(target.videoId, target.jumpTimestamp);
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
            disabled={historyLoading}
            className="w-full ark-chamfer-sm py-2.5 px-4 inline-flex items-center justify-center gap-2 text-[13px] font-semibold bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF] active:scale-[0.99] transition-all cursor-pointer shadow-[0_6px_18px_rgba(23,209,255,0.28)]"
          >
            <MessageSquarePlus className="w-4 h-4" />
            新建战术问答
          </button>

          <div className="space-y-1.5 overflow-y-auto pr-0.5 flex-1">
            <div className="px-2 py-1 text-xs font-medium text-slate-500">
              最近对话
            </div>
            {historyLoading && <p role="status" className="px-2 py-1 text-xs text-slate-500">正在读取历史对话…</p>}
            {historyError && <p role="alert" className="px-2 py-1 text-xs text-rose-700">{historyError}</p>}
            {[...threads].sort((a, b) => (b.activityAt ?? 0) - (a.activityAt ?? 0)).map((thread) => {
              const isActive = thread.id === activeThreadId;
              return (
                <div
                  key={thread.id}
                  onClick={() => selectThread(thread.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.target !== e.currentTarget) return;
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
                  <button type="button" aria-label={`重命名对话 ${thread.title}`}
                    onClick={e => renameThread(thread, e)}
                    className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1 rounded-md text-slate-400 hover:text-slate-700 cursor-pointer shrink-0">
                    <Pencil className="w-3.5 h-3.5" />
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
      <section className="flex-1 min-w-0 h-[calc(100dvh-8rem)] min-h-96 lg:h-auto lg:min-h-0 glass-panel-elevated rounded-2xl flex flex-col overflow-hidden relative">
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
                  title="仅检索所选游戏；未知归属的视频只在全部范围中检索"
                  disabled={isThinking}
                  onClick={() => updateScope({ gameScope: game, categoryScope: 'all' })}
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
            {[{ id: 'all' as const, label: '全部库' }, ...games.filter(g => gameScope === 'all' || g.id === gameScope).flatMap(g => g.categories)].map((opt) => {
              const active = selectedScope === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  disabled={isThinking}
                  onClick={() => updateScope({ categoryScope: opt.id })}
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
        <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} className="h-full overflow-y-auto overflow-x-hidden px-4 sm:px-8 py-6 [overflow-anchor:none]"
          onScroll={event => {
            const bottom = atBottom(event.currentTarget);
            followLatest.current = bottom;
            setAwayFromBottom(!bottom);
          }}
          onWheel={event => {
            if (event.deltaY < 0 && event.currentTarget.scrollTop > 4) followLatest.current = false;
          }}>
          <div ref={scrollContentRef} className="flex min-h-full min-w-0 flex-col">
          {!DEMO_MODE && (historyLoading || activeThread?.loaded === false) ? (
            <p role="status" className="py-10 text-center text-sm text-slate-500">正在读取会话…</p>
          ) : !activeThread || activeThread.messages.length === 0 ? (
            /* Clean Mainstream AI Welcome / Empty Chat State */
            <div className="flex flex-1 flex-col items-center justify-center max-w-2xl mx-auto text-center py-8 space-y-7">
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
            <div className="w-full min-w-0 max-w-4xl mx-auto space-y-7">
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
                const isTraceExpanded = !!msg.pending || !!expandedTraceMsgIds[msg.id];
                const sourceChunks = scenario?.retrievedChunks ?? (msg.citations || []).map((cite, idx) =>
                  presentCitation(cite, idx, msg.candidates?.find(video => video.bvid === cite.video_id)));
                const firstCitationByVideo = new Map<string, RetrievedChunk>();
                for (const chunk of sourceChunks) {
                  if (chunk.videoId && !firstCitationByVideo.has(chunk.videoId)) {
                    firstCitationByVideo.set(chunk.videoId, chunk);
                  }
                }
                const sourceVideos = Array.from(firstCitationByVideo, ([videoId, chunk]) => {
                  const libraryVideo = videos.find(video => video.id === videoId);
                  return {
                    id: videoId,
                    title: libraryVideo?.title || chunk.videoTitle,
                    thumbnail: libraryVideo?.thumbnail || chunk.thumbnail,
                    creator: libraryVideo?.creator || chunk.creator,
                    publishedAt: libraryVideo?.publishedAt || chunk.publishedAt,
                    stageCode: libraryVideo?.stageCode || chunk.stageCode,
                    url: biliUrl(videoId),
                  };
                });
                const localSourceHref = (chunk: RetrievedChunk) => `#source-${msg.id}-${chunk.id}`;
                const liveSteps: import('../types/strategy').AgentStep[] = (msg.steps || []).map(step => ({
                  id: step.stage, label: STAGE_LABELS[step.stage] || step.stage, findings: step.message,
                  durationText: STATUS_LABELS[step.status] || step.status, detail: '',
                }));
                const steps = scenario?.agentSteps ?? liveSteps;
                const markup = !scenario ? renderMarkdown(msg.content.replace(/\[引用([0-9]{1,6})\]/g, (ref, n) => {
                  const chunk = sourceChunks[Number(n) - 1];
                  const label = msg.citations?.[Number(n) - 1]?.external ? 'B 站来源' : '来源';
                  return chunk?.videoId ? `[${label} ${n}](${chunk.sourceUrl || localSourceHref(chunk)})` : ref;
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
                      {(msg.pending || steps.length > 0) && (
                        <div>
                          <button
                            type="button"
                            aria-expanded={isTraceExpanded}
                            aria-controls={`trace-${msg.id}`}
                            disabled={msg.pending}
                            onClick={() => toggleTrace(msg.id)}
                            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/75 enabled:hover:bg-white border border-slate-200/80 text-xs text-slate-700 transition-colors enabled:cursor-pointer"
                          >
                            <Cpu className="w-3.5 h-3.5 text-[#008DB3]" />
                            <span className="font-medium">
                              {msg.pending ? '执行中' : '已结束'}{steps.length > 0 && ` · ${steps.length} 步检索与校验`}
                            </span>
                            {sourceChunks.length > 0 && <span className="text-[#008DB3] font-mono tabular-nums">
                              · 引用 {sourceChunks.length} 段切片
                            </span>}
                            <ChevronDown
                              className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-150 ${
                                isTraceExpanded ? 'rotate-180' : ''
                              }`}
                            />
                          </button>

                          {isTraceExpanded && (
                            <div id={`trace-${msg.id}`} className="mt-2.5 p-4 rounded-xl bg-white/70 border border-slate-200/75 space-y-2.5">
                              {msg.pending && (
                                <p role="status" className={steps.length && !msg.confirmation ? 'sr-only' : 'text-xs text-slate-500'}>
                                  {msg.confirmation ? '等待选择是否转写音轨…' : (msg.steps || []).at(-1)?.message || '正在提交问题…'}
                                </p>
                              )}
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
                                  <span className={`inline-flex items-center gap-1.5 font-mono tabular-nums shrink-0 ${msg.pending && step.durationText === STATUS_LABELS.running ? 'font-medium text-[#008DB3]' : 'text-slate-400'}`}>
                                    {msg.pending && step.durationText === STATUS_LABELS.running && (
                                      <span aria-hidden="true" className="size-1.5 rounded-full bg-[#17D1FF] motion-safe:animate-pulse" />
                                    )}
                                    {step.durationText}
                                  </span>
                                </div>
                              ))}
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
                            </div>
                          )}
                        </div>
                      )}

                      {/* Main Answer Prose & Structured Strategy Content */}
                      {(scenario || msg.content || msg.error) && <div className="glass-panel rounded-2xl p-5 sm:p-6 space-y-5">
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
                                              openCitation(
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
                              onClick={event => {
                                if (!(event.target instanceof Element)) return;
                                const href = event.target.closest('a')?.getAttribute('href');
                                const chunk = sourceChunks.find(item => item.videoId && localSourceHref(item) === href);
                                if (!chunk) return;
                                event.preventDefault();
                                openCitation(chunk.citationIndex, sourceChunks);
                              }}
                              dangerouslySetInnerHTML={{ __html: markup }} />}
                            {msg.error && <p role="alert" className="text-sm text-rose-700">{msg.error}</p>}
                          </>
                        )}
                      </div>}

                      {sourceVideos.length > 0 && (
                        <div className="space-y-2.5">
                          <p className="text-xs font-medium text-slate-500">参考攻略视频</p>
                          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            {sourceVideos.map(video => {
                              const className = 'glass-panel flex h-full w-full items-center gap-3 rounded-xl p-3 text-left transition-colors hover:bg-white/95';
                              const label = <>
                                <div className="relative aspect-video w-24 shrink-0 overflow-hidden rounded-lg bg-slate-100">
                                  <ResilientImage
                                    key={video.thumbnail}
                                    src={video.thumbnail}
                                    alt=""
                                    className="h-full w-full object-cover"
                                    fallbackLabel={video.stageCode || '攻略视频'}
                                  />
                                </div>
                                <div className="min-w-0 flex-1 space-y-1">
                                  {(video.creator || video.publishedAt) && (
                                    <p className="truncate text-[11px] font-semibold text-[#008DB3]">
                                      {[video.creator, video.publishedAt].filter(Boolean).join(' · ')}
                                    </p>
                                  )}
                                  <p className="line-clamp-2 text-xs font-medium text-slate-900">{video.title}</p>
                                </div>
                              </>;
                              return (
                                <li key={video.id} className="min-w-0">
                                  {video.url
                                    ? <a className={className} title={video.title} href={video.url}
                                        target="_blank" rel="noopener noreferrer">{label}</a>
                                    : <button className={`${className} cursor-pointer`} title={video.title}
                                        type="button" onClick={() => onInspectVideo(video.id)}>{label}</button>}
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      )}
                      {msg.candidates && !(msg.pending && msg.confirmation) &&
                        <ExternalCandidates videos={msg.candidates} details={msg.searchDetails} pending={msg.pending} />}
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

            </div>
          )}
          </div>
        </div>
          {awayFromBottom && (
            <button type="button" aria-label="回到底部" title="回到底部" onClick={jumpToBottom}
              className="absolute bottom-3 left-1/2 z-10 grid size-9 -translate-x-1/2 place-items-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-md transition-colors hover:border-[#17D1FF] hover:text-[#008DB3] focus-visible:outline-2 focus-visible:outline-[#008DB3]">
              <ArrowDown aria-hidden="true" className="size-4" />
            </button>
          )}
        </div>

        {/* Bottom-Docked Unified Chat Input Composer */}
        <div className="px-4 sm:px-8 py-4 border-t border-slate-200/70 bg-white/70 backdrop-blur-xl shrink-0">
          <form onSubmit={handleComposerSubmit} className="max-w-4xl mx-auto space-y-2.5">
            {limitedVideo && (
              <div className="px-3 py-1.5 rounded-lg bg-[#17D1FF]/12 border border-[#17D1FF]/35 flex items-center justify-between gap-3 text-xs">
                <span className="text-slate-800 truncate flex items-center gap-1.5">
                  <PlayCircle className="w-3.5 h-3.5 text-[#008DB3] shrink-0" />
                  仅检索此视频：<strong className="font-semibold">{limitedVideo?.title}</strong>
                </span>
                <button
                  type="button"
                  disabled={isThinking}
                  onClick={() => { updateScope({ videoScope: undefined }); onClearScopedVideo(); }}
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
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <ComposerSwitch checked={agentMode} endfield={isEndfieldComposer} icon={Compass} label="战术推演"
                    disabled={isThinking || !activeThread || (!DEMO_MODE && !activeThread.loaded)}
                    title={activeThread?.gameState?.turn ? `当前回合：${activeThread.gameState.turn}` : '开启对局 Agent，根据回合、资源与可选动作给出建议'}
                    onClick={() => activeThread && changeThread(activeThread, { agentEnabled: !agentMode }, { agent_enabled: !agentMode })} />
                  {!DEMO_MODE && (
                    <ComposerSwitch checked={webSearch} endfield={isEndfieldComposer} icon={Globe} label="联网搜索"
                      title="允许本次搜索 B 站；下载和转写仍需另行确认"
                      onClick={() => setWebSearch(enabled => !enabled)} />
                  )}
                </div>
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
