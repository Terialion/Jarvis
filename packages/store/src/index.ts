// ============================================================================
// @jarvis/store — Persistence layer: JSONL session store + Markdown memory store
// ============================================================================

export { SessionStore } from './session.js';
export type { SessionRecord, SessionSidecar, TurnRecord } from './session.js';
export { MarkdownMemoryStore } from './memory.js';
export type { MemoryEntry } from './memory.js';
export { RolloutRecorder } from './rollout.js';
export type { RolloutItem, RolloutHeader, InitialHistoryType } from './rollout.js';

// ============================================================================
// ThreadStore — generic interface for session/thread persistence
// Pattern from Codex thread-store/ trait
// ============================================================================

export interface ThreadMeta {
  id: string;
  title: string | null;
  createdAt: string;
  updatedAt: string;
  modelName: string;
  turnCount: number;
}

export interface ThreadStore {
  createThread(meta: Partial<ThreadMeta> & { id: string }): Promise<ThreadMeta>;
  resumeThread(id: string): Promise<{ meta: ThreadMeta; messages: Array<{ role: string; content: string }> }>;
  loadHistory(id: string, limit?: number): Promise<Array<{ role: string; content: string; tool_call_id?: string }>>;
  listThreads(filter?: { archived?: boolean; limit?: number }): Promise<ThreadMeta[]>;
  updateMetadata(id: string, meta: Partial<ThreadMeta>): Promise<void>;
  archiveThread(id: string): Promise<void>;
}
