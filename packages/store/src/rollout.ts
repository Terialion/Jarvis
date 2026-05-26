// ============================================================================
// RolloutRecorder — structured per-turn recording with replay support
// Pattern from Codex rollout/ subsystem
// ============================================================================

import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as os from 'node:os';

// ============================================================================
// Types
// ============================================================================

export type InitialHistoryType = 'New' | 'Resumed' | 'Cleared' | 'Forked';

export interface RolloutItem {
  type: 'event' | 'response' | 'compaction' | 'turn_context' | 'branch';
  timestamp: string;
  turnId: string;
  sessionId: string;
  data: Record<string, unknown>;
  // For compaction items
  compactionStage?: string;
  tokensBefore?: number;
  tokensAfter?: number;
}

export interface RolloutHeader {
  type: 'rollout_header';
  sessionId: string;
  startedAt: string;
  initialHistory: InitialHistoryType;
  parentSessionId?: string;
  forkedFromEntryId?: string;
}

// ============================================================================
// RolloutRecorder
// ============================================================================

export class RolloutRecorder {
  private readonly rolloutDir: string;
  private sessionId: string | null = null;
  private filePath: string | null = null;
  private items: RolloutItem[] = [];

  constructor(baseDir: string = '~/.jarvis/rollouts') {
    this.rolloutDir = baseDir.startsWith('~/')
      ? path.join(os.homedir(), baseDir.slice(2))
      : baseDir;
  }

  /** Start recording a new rollout for a session. */
  async start(sessionId: string, initialHistory: InitialHistoryType = 'New', opts?: {
    parentSessionId?: string;
    forkedFromEntryId?: string;
  }): Promise<void> {
    this.sessionId = sessionId;
    this.items = [];

    const header: RolloutHeader = {
      type: 'rollout_header',
      sessionId,
      startedAt: new Date().toISOString(),
      initialHistory,
      parentSessionId: opts?.parentSessionId,
      forkedFromEntryId: opts?.forkedFromEntryId,
    };

    await fs.mkdir(this.rolloutDir, { recursive: true });
    this.filePath = path.join(this.rolloutDir, `${sessionId}.rollout.jsonl`);
    await fs.appendFile(this.filePath, JSON.stringify(header) + '\n', 'utf-8');
  }

  /** Record a rollout item (event, response, compaction, etc.). */
  async record(item: Omit<RolloutItem, 'timestamp' | 'sessionId'>): Promise<void> {
    if (!this.filePath || !this.sessionId) return;

    const full: RolloutItem = {
      ...item,
      timestamp: new Date().toISOString(),
      sessionId: this.sessionId,
    };

    this.items.push(full);
    await fs.appendFile(this.filePath, JSON.stringify(full) + '\n', 'utf-8');
  }

  /** Record a turn completion event. */
  async recordTurn(turnId: string, turnResult: Record<string, unknown>): Promise<void> {
    await this.record({
      type: 'turn_context',
      turnId,
      data: {
        turnId,
        finalAnswer: turnResult['finalAnswer'],
        stopReason: turnResult['stopReason'],
        skillsUsed: turnResult['skillsUsed'],
        toolCallCount: Array.isArray(turnResult['toolCalls']) ? turnResult['toolCalls'].length : 0,
        outputType: turnResult['outputType'],
      },
    });
  }

  /** Record a compaction event. */
  async recordCompaction(
    turnId: string,
    report: { stage: string; tokensBefore: number; tokensAfter: number; messagesBefore: number; messagesAfter: number },
  ): Promise<void> {
    await this.record({
      type: 'compaction',
      turnId,
      compactionStage: report.stage,
      tokensBefore: report.tokensBefore,
      tokensAfter: report.tokensAfter,
      data: {
        messagesBefore: report.messagesBefore,
        messagesAfter: report.messagesAfter,
      },
    });
  }

  /** Load a rollout from disk. */
  async load(sessionId: string): Promise<RolloutItem[]> {
    const filePath = path.join(this.rolloutDir, `${sessionId}.rollout.jsonl`);
    try {
      const raw = await fs.readFile(filePath, 'utf-8');
      const items: RolloutItem[] = [];
      for (const line of raw.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const obj = JSON.parse(trimmed);
          if (obj['type'] !== 'rollout_header') {
            items.push(obj as RolloutItem);
          }
        } catch { /* skip malformed */ }
      }
      return items;
    } catch {
      return [];
    }
  }

  /** Get all items from the current session. */
  getAllItems(): RolloutItem[] {
    return [...this.items];
  }

  /** Number of items recorded so far. */
  get count(): number {
    return this.items.length;
  }

  /** Stop recording. */
  async stop(): Promise<void> {
    this.sessionId = null;
    this.filePath = null;
    this.items = [];
  }
}
