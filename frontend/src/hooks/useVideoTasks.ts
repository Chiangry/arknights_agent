import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchVideos, importCachedTranscript, setTaskPaused, subscribeTask } from '../api/videos';
import type { AudioImportOption } from '../types/backend';
import type { StrategyVideo } from '../types/strategy';
import { presentVideo } from '../data/backendPresentation';

export function useVideoTasks(enabled: boolean) {
  const [library, setLibrary] = useState<StrategyVideo[]>([]);
  const [tasks, setTasks] = useState<Record<string, StrategyVideo>>({});
  const [origins, setOrigins] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const subscriptions = useRef(new Map<string, () => void>());
  const refreshId = useRef(0);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    const id = ++refreshId.current;
    try {
      const videos = await fetchVideos();
      if (id !== refreshId.current) return;
      setLibrary(videos.map(presentVideo));
      setError('');
    } catch (err) {
      if (id === refreshId.current) setError(err instanceof Error ? err.message : '无法读取知识库');
    }
  }, [enabled]);

  useEffect(() => {
    void refresh();
    return () => {
      ++refreshId.current;
      subscriptions.current.forEach(close => close());
      subscriptions.current.clear();
    };
  }, [refresh]);

  const track = (taskId: string, video: StrategyVideo, origin?: string) => {
    if (origin) setOrigins(prev => ({ ...prev, [origin]: taskId }));
    if (subscriptions.current.has(taskId)) return;
    setTasks(prev => ({ ...prev, [taskId]: { ...video, id: taskId, taskId } }));
    const update = (patch: Partial<StrategyVideo>) => setTasks(prev => ({
      ...prev, [taskId]: { ...prev[taskId], ...patch },
    }));
    subscriptions.current.set(taskId, subscribeTask(taskId, snap => {
      update({
        status: snap.status === 'done' ? 'indexed' : snap.status,
        progress: snap.pct, progressStage: snap.error || snap.message, chunkCount: snap.chunk_count || 0,
        paused: snap.paused, pauseRequested: snap.pause_requested, taskVideoId: snap.video_id || undefined,
      });
    }, snap => {
      subscriptions.current.delete(taskId);
      if (snap.status === 'done') void refresh();
    }, () => {
      subscriptions.current.delete(taskId);
      update({ status: 'error', progressStage: '进度连接中断，可刷新知识库检查结果' });
    }));
  };

  const saveTranscript = async (video: AudioImportOption) => {
    const result = await importCachedTranscript(video);
    if (result.status === 'exists') {
      void refresh();
      return;
    }
    track(result.task_id, {
      ...presentVideo({ video_id: video.bvid, title: video.title, author: video.author,
        source: '音频转写', duration: 0, chunk_count: 0 }),
      status: 'queued', progress: 0, progressStage: '等待处理',
    }, video.bvid);
    return result.task_id;
  };

  const pause = async (taskId: string, next: boolean) => {
    const snap = await setTaskPaused(taskId, next);
    setTasks(prev => prev[taskId] ? ({
      ...prev, [taskId]: { ...prev[taskId], paused: snap.paused, pauseRequested: snap.pause_requested },
    }) : prev);
  };

  const indexedIds = new Set(library.map(video => video.id));
  const queue = Object.values(tasks).filter(video =>
    !(video.status === 'indexed' && video.taskVideoId && indexedIds.has(video.taskVideoId)));
  const transcriptTasks = Object.fromEntries(Object.entries(origins).map(([bvid, id]) => [bvid, tasks[id]]));
  return { library, queue, error, refresh, track, pause, saveTranscript, transcriptTasks };
}
