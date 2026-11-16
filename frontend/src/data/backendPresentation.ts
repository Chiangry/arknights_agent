import type { Citation, Video } from '../types/backend';
import type { RetrievedChunk, StrategyVideo } from '../types/strategy';
import { THUMB_STAGE } from './mockStrategyData';

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export function timecode(seconds: number) {
  const total = Math.max(0, Math.floor(seconds || 0));
  return [Math.floor(total / 60), total % 60].map((n) => String(n).padStart(2, '0')).join(':');
}

export function biliUrl(bvid: string | null, seconds = 0) {
  return bvid && /^BV[0-9A-Za-z]{10}$/.test(bvid)
    ? `https://www.bilibili.com/video/${bvid}/?t=${Math.max(0, Math.floor(seconds || 0))}`
    : undefined;
}

export function presentVideo(video: Video): StrategyVideo {
  return {
    id: video.video_id, bvId: biliUrl(video.video_id) ? video.video_id : '本地文件',
    title: video.title || video.video_id, creator: video.author || '未知作者',
    category: 'main', categoryLabel: video.source || '知识库视频', stageCode: '',
    duration: timecode(video.duration), publishedAt: '',
    indexedAt: video.created_at?.slice(0, 10),
    thumbnail: THUMB_STAGE, status: 'indexed', progress: 100, chunkCount: video.chunk_count,
    operatorCount: 0, keyframeCount: 0, summary: '已建立字幕或转写片段索引，可在战术问答中检索。',
    operators: [], extractedHighlights: [], backend: true, sourceUrl: biliUrl(video.video_id),
  };
}

export function presentCitation(cite: Citation, index: number, video?: { cover?: string; pubdate?: number }): RetrievedChunk {
  return {
    id: String(index + 1), citationIndex: index + 1, videoId: cite.video_id || '',
    videoTitle: cite.title || '视频片段', creator: cite.author || (cite.external ? 'B 站补查' : '知识库'),
    stageCode: '', timestampRange: `${timecode(cite.start)}–${timecode(cite.end)}`,
    jumpTimestamp: timecode(cite.start), thumbnail: video?.cover || THUMB_STAGE, excerpt: cite.text,
    publishedAt: video?.pubdate ? new Date(video.pubdate * 1000).toLocaleDateString('zh-CN') : undefined,
    matchedTerms: [], sourceUrl: biliUrl(cite.video_id, cite.start),
  };
}
