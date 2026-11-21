import type { VisualConfirmation, VisualCoverage } from './backend';

export type PageView = 'qa' | 'ingest' | 'library';

export type GameTitle = 'arknights' | 'endfield';
export type GameScope = 'all' | GameTitle;

export type KnowledgeCategory =
  | 'all'
  | 'unknown'
  | 'main'
  | 'roguelike'
  | 'cc'
  | 'operator'
  | 'aic'
  | 'exploration'
  | 'combo'
  | 'char';

export type VideoStatus = 'indexed' | 'processing' | 'queued' | 'error' | 'draft';

export interface StrategyVideo {
  id: string;
  game?: GameTitle;
  gameLabel?: string;
  bvId: string;
  title: string;
  creator: string;
  category: Exclude<KnowledgeCategory, 'all'>;
  categoryLabel: string;
  stageCode: string;
  duration: string;
  publishedAt: string;
  indexedAt?: string;
  thumbnail: string;
  status: VideoStatus;
  progress: number;
  progressStage?: string;
  backend?: boolean;
  taskId?: string;
  taskVideoId?: string;
  paused?: boolean;
  pauseRequested?: boolean;
  visualConfirmation?: VisualConfirmation;
  visualCoverage?: VisualCoverage;
  sourceUrl?: string;
  chunkCount: number;
  operatorCount: number;
  keyframeCount: number;
  summary: string;
  operators: string[];
  extractedHighlights: {
    timestamp: string;
    title: string;
    detail: string;
  }[];
}

export interface AgentStep {
  id: string;
  label: string;
  detail: string;
  durationText: string;
  findings: string;
  toolName?: string;
}

export interface DeploymentNode {
  order: string;
  timestamp: string;
  operator: string;
  profession: string;
  skill: string;
  direction: string;
  note: string;
  citationIndex: number;
}

export interface OperatorCardItem {
  name: string;
  profession: string;
  skillLabel: string;
  moduleNote: string;
  roleSummary: string;
}

export interface RetrievedChunk {
  id: string;
  game?: GameTitle;
  citationIndex: number;
  videoId: string;
  videoTitle: string;
  creator: string;
  evidenceSource?: string;
  publishedAt?: string;
  stageCode: string;
  timestampRange: string;
  jumpTimestamp: string;
  similarityScore?: number;
  thumbnail: string;
  excerpt: string;
  matchedTerms: string[];
  sourceUrl?: string;
}

export interface AgentAnalysisBlock {
  toolsUsed: { name: string; summary: string }[];
  crossCheckInsight: string;
  alternativeSubstitutions: {
    target: string;
    replacement: string;
    condition: string;
  }[];
}

export interface QaScenario {
  id: string;
  game: GameTitle;
  gameLabel: string;
  prompt: string;
  category: Exclude<KnowledgeCategory, 'all'>;
  headline: string;
  tacticalSummary: string;
  keyTakeaways: string[];
  agentSteps: AgentStep[];
  deploymentTimeline: DeploymentNode[];
  recommendedOperators: OperatorCardItem[];
  retrievedChunks: RetrievedChunk[];
  agentAnalysis?: AgentAnalysisBlock;
}

export interface CandidateVideoResult {
  id: string;
  game: GameTitle;
  gameLabel: string;
  bvId: string;
  title: string;
  creator: string;
  platform: string;
  duration: string;
  stageCode: string;
  category: Exclude<KnowledgeCategory, 'all'>;
  categoryLabel: string;
  thumbnail: string;
  views: string;
  publishedAt: string;
}
