// ============================================================================
// JSONL-based session store — append-only transcripts + sidecar JSON
// ============================================================================

import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as os from 'node:os';
import type { TurnStatus } from '@jarvis/shared';

// ============================================================================
// Types
// ============================================================================

/** Base record type — every JSONL line has at least these fields. */
export interface SessionRecord {
  type:
    | 'turn'
    | 'message'
    | 'tool_call'
    | 'tool_result'
    | 'summary'
    | 'skill_obs'
    | 'research_obs'
    | 'approval'
    | 'task_plan'
    | 'compaction_checkpoint'
    | 'branch_point'
    | 'fork_point';
  timestamp?: string; // ISO-8601 UTC, auto-set on write if missing
  [key: string]: unknown;
}

/** Turn record in the session JSONL. */
export interface TurnRecord extends SessionRecord {
  type: 'turn';
  event: 'start' | 'end' | 'status_change' | 'final_answer';
  turn_id: string;
  status: TurnStatus;
}

/** Mutable sidecar metadata for a session. */
export interface SessionSidecar {
  session_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  project_id: string | null;
  cwd: string | null;
}

// ============================================================================
// Helpers
// ============================================================================

function utcNow(): string {
  return new Date().toISOString();
}

function resolveHome(filePath: string): string {
  if (filePath.startsWith('~/')) {
    return path.join(os.homedir(), filePath.slice(2));
  }
  return filePath;
}

// Simple async mutex to serialize writes (Node.js is single-threaded, but
// concurrent async operations can interleave at await points).
class Mutex {
  private _locked = false;
  private _queue: Array<() => void> = [];

  async acquire(): Promise<void> {
    if (!this._locked) {
      this._locked = true;
      return;
    }
    return new Promise<void>((resolve) => {
      this._queue.push(resolve);
    });
  }

  release(): void {
    if (this._queue.length > 0) {
      const next = this._queue.shift()!;
      next();
    } else {
      this._locked = false;
    }
  }
}

// ============================================================================
// SessionStore
// ============================================================================

export class SessionStore {
  private readonly sessionsDir: string;
  private readonly _cache: Map<string, SessionRecord[]> = new Map();
  private readonly _sidecarCache: Map<string, SessionSidecar> = new Map();
  private readonly _writeLock = new Mutex();

  constructor(baseDir: string = '~/.jarvis/sessions') {
    this.sessionsDir = resolveHome(baseDir);
  }

  // ── Path helpers ────────────────────────────────────────────────────

  private _jsonlPath(sessionId: string): string {
    return path.join(this.sessionsDir, `${sessionId}.jsonl`);
  }

  private _sidecarPath(sessionId: string): string {
    return path.join(this.sessionsDir, `${sessionId}.json`);
  }

  // ── Cache management ────────────────────────────────────────────────

  private async _ensureLoaded(sessionId: string): Promise<SessionRecord[]> {
    if (!this._cache.has(sessionId)) {
      const records = await this._readJsonl(sessionId);
      this._cache.set(sessionId, records);
    }
    return this._cache.get(sessionId)!;
  }

  private async _readJsonl(sessionId: string): Promise<SessionRecord[]> {
    const filePath = this._jsonlPath(sessionId);
    try {
      const raw = await fs.readFile(filePath, 'utf-8');
      const lines: SessionRecord[] = [];
      for (const line of raw.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const obj = JSON.parse(trimmed);
          if (typeof obj === 'object' && obj !== null) {
            lines.push(obj as SessionRecord);
          }
        } catch {
          // Skip malformed lines (matches Python behavior)
        }
      }
      return lines;
    } catch {
      return [];
    }
  }

  // ── Sidecar (mutable state) ─────────────────────────────────────────

  private async _loadSidecar(sessionId: string): Promise<SessionSidecar> {
    if (this._sidecarCache.has(sessionId)) {
      return this._sidecarCache.get(sessionId)!;
    }
    const filePath = this._sidecarPath(sessionId);
    try {
      const raw = await fs.readFile(filePath, 'utf-8');
      const data = JSON.parse(raw) as SessionSidecar;
      this._sidecarCache.set(sessionId, data);
      return data;
    } catch {
      const now = utcNow();
      const data: SessionSidecar = {
        session_id: sessionId,
        title: null,
        created_at: now,
        updated_at: now,
        project_id: null,
        cwd: null,
      };
      this._sidecarCache.set(sessionId, data);
      return data;
    }
  }

  private async _saveSidecar(sessionId: string): Promise<void> {
    const data = this._sidecarCache.get(sessionId);
    if (data) {
      data.updated_at = utcNow();
      const filePath = this._sidecarPath(sessionId);
      await fs.mkdir(path.dirname(filePath), { recursive: true });
      await fs.writeFile(filePath, JSON.stringify(data, null, 2), 'utf-8');
    }
  }

  private async _touchSidecar(sessionId: string): Promise<void> {
    const data = await this._loadSidecar(sessionId);
    data.updated_at = utcNow();
    await this._saveSidecar(sessionId);
  }

  // ── Internal: append one line (JSONL) ───────────────────────────────

  private async _appendLine(
    sessionId: string,
    obj: Record<string, unknown>,
  ): Promise<void> {
    await this._writeLock.acquire();
    try {
      // Auto-stamp timestamp if not present (matches Python setdefault)
      if (!('timestamp' in obj) || typeof obj.timestamp !== 'string') {
        obj.timestamp = utcNow();
      }
      const line = JSON.stringify(obj) + '\n';
      const filePath = this._jsonlPath(sessionId);
      await fs.mkdir(path.dirname(filePath), { recursive: true });
      await fs.appendFile(filePath, line, 'utf-8');

      // Update in-memory cache if loaded
      if (this._cache.has(sessionId)) {
        this._cache.get(sessionId)!.push(obj as SessionRecord);
      }
    } finally {
      this._writeLock.release();
    }
  }

  // ── Session lifecycle ───────────────────────────────────────────────

  /** Create a new session: initializes the sidecar JSON metadata file. */
  async createSession(
    sessionId: string,
    meta?: Partial<SessionSidecar>,
  ): Promise<void> {
    const now = utcNow();
    const sidecar: SessionSidecar = {
      session_id: sessionId,
      title: meta?.title ?? null,
      created_at: meta?.created_at ?? now,
      updated_at: meta?.updated_at ?? now,
      project_id: meta?.project_id ?? null,
      cwd: meta?.cwd ?? null,
    };
    this._sidecarCache.set(sessionId, sidecar);
    await this._saveSidecar(sessionId);
  }

  /** Append a single record to the session JSONL. */
  async appendRecord(sessionId: string, record: SessionRecord): Promise<void> {
    await this._appendLine(sessionId, record as Record<string, unknown>);
    await this._touchSidecar(sessionId);
  }

  /** Read all records, optionally filtered by type. */
  async getRecords(
    sessionId: string,
    filter?: { type?: string },
  ): Promise<SessionRecord[]> {
    const records = await this._ensureLoaded(sessionId);
    if (filter?.type) {
      return records.filter((r) => r.type === filter.type);
    }
    return [...records];
  }

  /** Read the sidecar JSON for a session. */
  async getSidecar(sessionId: string): Promise<SessionSidecar> {
    return await this._loadSidecar(sessionId);
  }

  /** Merge updates into the sidecar JSON. */
  async updateSidecar(
    sessionId: string,
    update: Partial<SessionSidecar>,
  ): Promise<void> {
    const data = await this._loadSidecar(sessionId);
    if (update.title !== undefined) data.title = update.title;
    if (update.created_at !== undefined) data.created_at = update.created_at;
    if (update.project_id !== undefined) data.project_id = update.project_id;
    if (update.cwd !== undefined) data.cwd = update.cwd;
    // updated_at is auto-set in _saveSidecar
    this._sidecarCache.set(sessionId, data);
    await this._saveSidecar(sessionId);
  }

  /** List all session IDs found in baseDir. */
  async listSessions(): Promise<string[]> {
    try {
      const entries = await fs.readdir(this.sessionsDir, {
        withFileTypes: true,
      });
      const ids = new Set<string>();
      for (const entry of entries) {
        if (entry.isFile() && entry.name.endsWith('.jsonl')) {
          ids.add(entry.name.slice(0, -6)); // strip .jsonl
        }
      }
      // Also include sidecar-only sessions (created but empty)
      for (const entry of entries) {
        if (entry.isFile() && entry.name.endsWith('.json')) {
          const sid = entry.name.slice(0, -5); // strip .json
          if (!ids.has(sid)) {
            ids.add(sid);
          }
        }
      }
      return [...ids].sort();
    } catch {
      return [];
    }
  }

  /**
   * Enforce a disk budget for sessions by removing the oldest sessions
   * until the total is under maxBytes. Uses file mtime for ordering.
   */
  async enforceSessionDiskBudget(maxBytes: number): Promise<{ removed: number; freedBytes: number }> {
    let removed = 0;
    let freedBytes = 0;

    try {
      const entries = await fs.readdir(this.sessionsDir, { withFileTypes: true });
      const files = entries
        .filter((e) => e.isFile() && (e.name.endsWith('.jsonl') || e.name.endsWith('.json')))
        .map((e) => ({
          name: e.name,
          path: path.join(this.sessionsDir, e.name),
        }));

      // Get sizes and sort by name (which includes timestamps for session IDs)
      const withSizes: Array<{ name: string; path: string; size: number }> = [];
      let totalSize = 0;
      for (const f of files) {
        try {
          const stat = await fs.stat(f.path);
          withSizes.push({ ...f, size: stat.size });
          totalSize += stat.size;
        } catch {
          withSizes.push({ ...f, size: 0 });
        }
      }

      if (totalSize <= maxBytes) return { removed: 0, freedBytes: 0 };

      // Sort by name (oldest sessions first — session IDs are sortable timestamps)
      withSizes.sort((a, b) => a.name.localeCompare(b.name));

      for (const f of withSizes) {
        if (totalSize <= maxBytes * 0.8) break; // Soft cap at 80%
        try {
          await fs.unlink(f.path);
          totalSize -= f.size;
          freedBytes += f.size;
          removed++;
        } catch { /* skip unremovable */ }
      }

      // Invalidate caches for removed sessions
      for (const f of withSizes.slice(0, removed)) {
        const sid = f.name.replace(/\.(jsonl|json)$/, '');
        this._cache.delete(sid);
        this._sidecarCache.delete(sid);
      }
    } catch { /* best-effort */ }

    return { removed, freedBytes };
  }

  /** Check whether a session exists. */
  async sessionExists(sessionId: string): Promise<boolean> {
    try {
      await fs.access(this._jsonlPath(sessionId));
      return true;
    } catch {
      // Check sidecar-only existence
      try {
        await fs.access(this._sidecarPath(sessionId));
        return true;
      } catch {
        return false;
      }
    }
  }

  // ── Session repair ─────────────────────────────────────────────────

  /**
   * Repair a corrupted session: remove unparseable JSONL lines,
   * rebuild sidecar from JSONL if sidecar is corrupted.
   * Returns repair report.
   */
  async repairSession(sessionId: string): Promise<{ repaired: boolean; issues: string[] }> {
    const issues: string[] = [];
    let repaired = false;

    // 1. Repair JSONL: remove malformed lines
    const jsonlPath = this._jsonlPath(sessionId);
    try {
      const raw = await fs.readFile(jsonlPath, 'utf-8');
      const lines = raw.split('\n');
      const validLines: string[] = [];
      let removedCount = 0;
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          JSON.parse(trimmed);
          validLines.push(trimmed);
        } catch {
          removedCount++;
          repaired = true;
        }
      }
      if (removedCount > 0) {
        issues.push(`Removed ${removedCount} malformed JSONL line(s)`);
        await this._writeLock.acquire();
        try {
          await fs.writeFile(jsonlPath, validLines.join('\n') + (validLines.length > 0 ? '\n' : ''), 'utf-8');
          // Invalidate cache so next read picks up fixed file
          this._cache.delete(sessionId);
        } finally {
          this._writeLock.release();
        }
      }
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== 'ENOENT') {
        issues.push(`JSONL read error: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    // 2. Repair sidecar: rebuild from JSONL if corrupted or missing
    const sidecarPath = this._sidecarPath(sessionId);
    let sidecarOk = false;
    try {
      const raw = await fs.readFile(sidecarPath, 'utf-8');
      JSON.parse(raw); // validate parseability
      sidecarOk = true;
    } catch {
      sidecarOk = false;
    }

    if (!sidecarOk) {
      // Rebuild sidecar from JSONL data
      try {
        const records = await this._readJsonl(sessionId);
        const firstRecord = records[0];
        const lastRecord = records[records.length - 1];
        const title = firstRecord
          ? String((firstRecord as Record<string, unknown>)['output_summary'] ?? '').slice(0, 80) || null
          : null;
        const sidecar: SessionSidecar = {
          session_id: sessionId,
          title,
          created_at: String(firstRecord?.timestamp ?? utcNow()),
          updated_at: String(lastRecord?.timestamp ?? utcNow()),
          project_id: null,
          cwd: null,
        };
        this._sidecarCache.set(sessionId, sidecar);
        await this._saveSidecar(sessionId);
        repaired = true;
        issues.push('Sidecar rebuilt from JSONL');
      } catch {
        // Can't rebuild — leave as-is
        issues.push('Sidecar missing and could not be rebuilt');
      }
    }

    return { repaired, issues };
  }

  /**
   * Truncate the session JSONL after compaction, removing message entries
   * before firstKeptMessageId while preserving non-message state entries
   * (compaction checkpoints, task plans, approvals, summaries, skill/research obs).
   * Must acquire write lock.
   */
  async truncateAfterCompaction(
    sessionId: string,
    firstKeptMessageId: string,
  ): Promise<{ removed: number; kept: number }> {
    await this._writeLock.acquire();
    try {
      const jsonlPath = this._jsonlPath(sessionId);
      let raw: string;
      try {
        raw = await fs.readFile(jsonlPath, 'utf-8');
      } catch {
        return { removed: 0, kept: 0 };
      }

      const allLines = raw.split('\n');
      const keptLines: string[] = [];
      let foundCutoff = false;
      let removed = 0;

      // Non-message types that should survive truncation even before cutoff
      const SURVIVING_TYPES = new Set([
        'compaction_checkpoint',
        'task_plan',
        'approval',
        'summary',
        'skill_obs',
        'research_obs',
      ]);

      for (const line of allLines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        try {
          const obj = JSON.parse(trimmed) as Record<string, unknown>;
          const recordType = String(obj['type'] ?? '');

          // Check if this is the cutoff message
          if (!foundCutoff && recordType === 'message') {
            const msgId = String(obj['message_id'] ?? '');
            if (msgId === firstKeptMessageId) {
              foundCutoff = true;
            }
          }

          if (!foundCutoff) {
            if (recordType === 'message' || recordType === 'tool_call' || recordType === 'tool_result') {
              removed++;
              continue; // Drop old messages/tool calls/results
            }
            if (SURVIVING_TYPES.has(recordType) || recordType === 'turn') {
              keptLines.push(trimmed); // Preserve state records
              continue;
            }
            removed++;
            continue;
          }

          keptLines.push(trimmed);
        } catch {
          // Skip unparseable lines
          removed++;
        }
      }

      // If cutoff not found, don't truncate
      if (!foundCutoff) {
        return { removed: 0, kept: allLines.filter((l) => l.trim()).length };
      }

      await fs.writeFile(
        jsonlPath,
        keptLines.join('\n') + (keptLines.length > 0 ? '\n' : ''),
        'utf-8',
      );

      // Invalidate cache
      this._cache.delete(sessionId);

      return { removed, kept: keptLines.length };
    } finally {
      this._writeLock.release();
    }
  }

  /** Create or resume a session from ChatInput-style data. */
  async createOrResumeSession(input: {
    sessionId?: string | null;
    text?: string | null;
    projectId?: string | null;
    cwd?: string | null;
  }): Promise<{ session_id: string; project_id: string | null; cwd: string | null }> {
    const sessionId = input.sessionId || `session_${crypto.randomUUID().slice(0, 12)}`;

    // Auto-repair existing sessions on resume
    if (input.sessionId) {
      await this.repairSession(sessionId).catch(() => { /* best-effort */ });
    }

    await this.createSession(sessionId, {
      title: (input.text ?? '').trim().slice(0, 80) || null,
      project_id: input.projectId ?? null,
      cwd: input.cwd ?? null,
    });
    return { session_id: sessionId, project_id: input.projectId ?? null, cwd: input.cwd ?? null };
  }

  // ── Turn lifecycle ────────────────────────────────────────────────

  async createTurn(
    sessionId: string,
    status: string = 'running',
    metadata?: Record<string, unknown>,
  ): Promise<{ turn_id: string; session_id: string; status: string }> {
    const turnId = `turn_${crypto.randomUUID().slice(0, 12)}`;
    await this._appendLine(sessionId, {
      type: 'turn',
      event: 'start',
      turn_id: turnId,
      status,
    });
    await this._touchSidecar(sessionId);
    return { turn_id: turnId, session_id: sessionId, status };
  }

  async endTurn(
    sessionId: string,
    agentResult: {
      turnId?: string;
      finalAnswer?: string;
      summary?: { human?: string; machine?: Record<string, unknown> } | Record<string, unknown>;
      outputType?: string;
      stopReason?: string;
      skillsUsed?: string[];
      toolCalls?: unknown[];
      events?: unknown[];
      status?: string;
    },
  ): Promise<Record<string, unknown>> {
    const summary = (agentResult.summary ?? {}) as Record<string, unknown>;
    const summaryHuman = String(summary.human ?? agentResult.finalAnswer ?? '').slice(0, 1200);
    const turnData: Record<string, unknown> = {
      type: 'turn',
      event: 'end',
      turn_id: agentResult.turnId ?? '',
      input: '',
      output_summary: summaryHuman,
      output_type: agentResult.outputType ?? '',
      stop_reason: agentResult.stopReason ?? '',
      skills_used: agentResult.skillsUsed ?? [],
      tool_calls_count: (agentResult.toolCalls ?? []).length,
      events_count: (agentResult.events ?? []).length,
      status: agentResult.status ?? 'completed',
    };
    await this._appendLine(sessionId, turnData);
    await this._touchSidecar(sessionId);
    return turnData;
  }

  async updateTurnStatus(
    sessionId: string,
    turnId: string,
    status: string,
  ): Promise<void> {
    await this._appendLine(sessionId, {
      type: 'turn',
      event: 'status_change',
      turn_id: turnId,
      status,
    });
    await this._touchSidecar(sessionId);
  }

  async getRecentTurns(
    sessionId: string,
    limit: number = 10,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const turnData: Map<string, Record<string, unknown>> = new Map();
    for (const l of lines) {
      if (l.type !== 'turn') continue;
      const tid = String(l.turn_id ?? '');
      if (!turnData.has(tid)) {
        turnData.set(tid, {
          turn_id: tid,
          thread_id: sessionId,
          input_redacted: '',
          output_summary_redacted: '',
          output_type: '',
          stop_reason: null,
          created_at: l.timestamp ?? '',
          metadata: { status: '', skills_used: [] },
        });
      }
      const entry = turnData.get(tid)!;
      const event = String(l.event ?? '');
      if (event === 'start') {
        (entry.metadata as Record<string, unknown>).status = l.status;
      } else if (event === 'end' || event === 'final_answer') {
        entry.input_redacted = (l.input ?? '') || entry.input_redacted;
        entry.output_summary_redacted = (l.output_summary ?? '') || entry.output_summary_redacted;
        entry.output_type = (l.output_type ?? '') || entry.output_type;
        entry.stop_reason = l.stop_reason || entry.stop_reason;
        (entry.metadata as Record<string, unknown>).status = (l.status ?? '') || (entry.metadata as Record<string, unknown>).status;
        (entry.metadata as Record<string, unknown>).skills_used = (l.skills_used ?? []) || (entry.metadata as Record<string, unknown>).skills_used;
      }
    }
    return [...turnData.values()].slice(-Math.max(1, limit));
  }

  // ── Messages ──────────────────────────────────────────────────────

  async appendMessage(
    sessionId: string,
    role: string,
    content: string,
    opts?: { turnId?: string; toolCallId?: string; metadata?: Record<string, unknown> },
  ): Promise<Record<string, unknown>> {
    const msg: Record<string, unknown> = {
      type: 'message',
      message_id: `msg_${crypto.randomUUID().slice(0, 12)}`,
      role,
      content,
      turn_id: opts?.turnId ?? null,
      metadata: opts?.metadata ?? {},
    };
    if (opts?.toolCallId) msg.tool_call_id = opts.toolCallId;
    await this._appendLine(sessionId, msg);
    await this._touchSidecar(sessionId);
    return msg;
  }

  async loadMessages(
    sessionId: string,
    limit: number = 40,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const msgLines = lines.filter((l) => l.type === 'message');
    const recent = msgLines.slice(-Math.max(1, limit));
    return recent.map((m) => ({
      message_id: m.message_id ?? '',
      session_id: sessionId,
      turn_id: m.turn_id,
      role: m.role ?? '',
      content: m.content ?? '',
      metadata: m.metadata ?? {},
      tool_call_id: m.tool_call_id,
    }));
  }

  async getRecentMessages(sessionId: string, limit: number = 20): Promise<Array<Record<string, unknown>>> {
    return this.loadMessages(sessionId, limit);
  }

  async countMessages(sessionId: string): Promise<number> {
    const lines = await this._ensureLoaded(sessionId);
    return lines.filter((l) => l.type === 'message').length;
  }

  // ── Tool calls ────────────────────────────────────────────────────

  async appendToolCall(
    sessionId: string,
    turnId: string,
    toolCall: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const call: Record<string, unknown> = {
      type: 'tool_call',
      call_id: String(toolCall.id ?? toolCall.call_id ?? `call_${crypto.randomUUID().slice(0, 12)}`),
      turn_id: turnId,
      tool_name: String(toolCall.name ?? ''),
      arguments: toolCall.arguments ?? {},
      status: 'requested',
    };
    await this._appendLine(sessionId, call);
    await this._touchSidecar(sessionId);
    return call;
  }

  async appendToolResult(
    sessionId: string,
    turnId: string,
    toolResult: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const result: Record<string, unknown> = {
      type: 'tool_result',
      call_id: String(toolResult.call_id ?? ''),
      turn_id: turnId,
      tool_name: String(toolResult.name ?? ''),
      ok: Boolean(toolResult.ok),
      content: toolResult.content ?? '',
      error: toolResult.error ?? null,
      status: Boolean(toolResult.ok) ? 'completed' : 'failed',
    };
    await this._appendLine(sessionId, result);
    await this._touchSidecar(sessionId);
    return result;
  }

  async getToolCalls(
    sessionId: string,
    limit: number = 20,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const calls: Map<string, Record<string, unknown>> = new Map();
    for (const l of lines) {
      if (l.type === 'tool_call') {
        const cid = String(l.call_id ?? '');
        if (!calls.has(cid)) {
          calls.set(cid, {
            call_id: cid,
            thread_id: sessionId,
            turn_id: l.turn_id ?? '',
            tool_name: l.tool_name ?? '',
            args_redacted: l.arguments ?? {},
            result_redacted: null,
            status: l.status ?? 'requested',
            created_at: l.timestamp ?? '',
          });
        }
      } else if (l.type === 'tool_result') {
        const cid = String(l.call_id ?? '');
        const entry = calls.get(cid);
        if (entry) {
          entry.result_redacted = { content: l.content, error: l.error, ok: l.ok };
          entry.status = l.status ?? 'completed';
        }
      }
    }
    return [...calls.values()].slice(-Math.max(1, limit));
  }

  // ── Summaries ─────────────────────────────────────────────────────

  async saveSummary(
    sessionId: string,
    turnId: string,
    summary: { human?: string; machine?: Record<string, unknown> },
  ): Promise<void> {
    await this._appendLine(sessionId, {
      type: 'summary',
      summary_id: `sum_${crypto.randomUUID().slice(0, 12)}`,
      turn_id: turnId,
      human: summary.human ?? '',
      machine: summary.machine ?? {},
    });
    await this._touchSidecar(sessionId);
  }

  async loadSummaries(
    sessionId: string,
    limit: number = 20,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const summaryLines = lines.filter((l) => l.type === 'summary');
    const recent = summaryLines.slice(-Math.max(1, limit));
    return recent.map((s) => ({
      summary_id: s.summary_id ?? '',
      session_id: sessionId,
      turn_id: s.turn_id ?? '',
      summary: { human: s.human ?? '', machine: s.machine ?? {} },
      created_at: s.timestamp ?? '',
    }));
  }

  // ── Branch / DAG support ──────────────────────────────────────────

  /**
   * Create a named branch point in the session. Stores a branch_point
   * entry that marks where a subagent or fork can branch from.
   */
  async createBranch(
    sessionId: string,
    branchName: string,
  ): Promise<{ branchId: string; entryIndex: number }> {
    await this._ensureLoaded(sessionId);
    const branchId = `branch_${crypto.randomUUID().slice(0, 12)}`;
    const records = this._cache.get(sessionId) ?? [];
    const entryIndex = records.length;
    await this._appendLine(sessionId, {
      type: 'branch_point',
      branch_id: branchId,
      branch_name: branchName,
      entry_index: entryIndex,
    });
    await this._touchSidecar(sessionId);
    return { branchId, entryIndex };
  }

  /** List all branch points in a session. */
  async getBranches(
    sessionId: string,
  ): Promise<Array<{ branchId: string; branchName: string; entryIndex: number; createdAt: string }>> {
    const lines = await this._ensureLoaded(sessionId);
    return lines
      .filter((l) => l.type === 'branch_point')
      .map((l) => ({
        branchId: String(l['branch_id'] ?? ''),
        branchName: String(l['branch_name'] ?? ''),
        entryIndex: Number(l['entry_index'] ?? 0),
        createdAt: String(l.timestamp ?? ''),
      }));
  }

  /**
   * Fork a session from a specific entry index, creating a new session
   * that starts from that point in history.
   */
  async forkSession(
    sessionId: string,
    fromEntryIndex: number,
    newSessionId?: string,
  ): Promise<string> {
    const records = await this._ensureLoaded(sessionId);
    const forkId = newSessionId ?? `fork_${crypto.randomUUID().slice(0, 12)}`;
    const prefixRecords = records.slice(0, fromEntryIndex);

    // Create the fork session and copy prefix records
    await this.createSession(forkId, {
      title: `Fork of ${sessionId}`,
      cwd: null,
    });

    for (const record of prefixRecords) {
      await this._appendLine(forkId, record as Record<string, unknown>);
    }

    // Mark the fork point
    await this._appendLine(forkId, {
      type: 'fork_point',
      forked_from: sessionId,
      forked_at_entry: fromEntryIndex,
    });

    return forkId;
  }

  // ── Compaction checkpoints ────────────────────────────────────────

  async saveCompactionCheckpoint(
    sessionId: string,
    checkpoint: {
      stage: string;
      tokensBefore: number;
      tokensAfter: number;
      messagesBefore: number;
      messagesAfter: number;
      firstKeptIndex?: number;
      trigger?: string;
    },
  ): Promise<void> {
    await this._appendLine(sessionId, {
      type: 'compaction_checkpoint',
      checkpoint_id: `cp_${crypto.randomUUID().slice(0, 12)}`,
      session_id: sessionId,
      stage: checkpoint.stage,
      tokens_before: checkpoint.tokensBefore,
      tokens_after: checkpoint.tokensAfter,
      messages_before: checkpoint.messagesBefore,
      messages_after: checkpoint.messagesAfter,
      first_kept_index: checkpoint.firstKeptIndex ?? null,
      trigger: checkpoint.trigger ?? 'budget',
    });
    await this._touchSidecar(sessionId);
  }

  async loadCompactionCheckpoints(
    sessionId: string,
    limit: number = 5,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const checkpointLines = lines.filter((l) => l.type === 'compaction_checkpoint');
    const recent = checkpointLines.slice(-Math.max(1, limit));
    return recent.map((c) => ({
      checkpoint_id: c.checkpoint_id ?? '',
      session_id: sessionId,
      stage: c.stage ?? '',
      tokens_before: Number(c.tokens_before ?? 0),
      tokens_after: Number(c.tokens_after ?? 0),
      messages_before: Number(c.messages_before ?? 0),
      messages_after: Number(c.messages_after ?? 0),
      first_kept_index: c.first_kept_index ?? null,
      trigger: c.trigger ?? 'budget',
      created_at: c.timestamp ?? '',
    }));
  }

  // ── Skill observations ────────────────────────────────────────────

  async appendSkillObs(
    sessionId: string,
    observation: {
      skill_name: string;
      summary: string;
      related_files?: string[];
      facts?: Record<string, unknown>;
      tool_calls?: string[];
      created_at?: string;
    },
    turnId?: string | null,
  ): Promise<Record<string, unknown>> {
    const obs: Record<string, unknown> = {
      type: 'skill_obs',
      observation_id: `skillobs_${crypto.randomUUID().slice(0, 12)}`,
      turn_id: turnId ?? null,
      skill_name: observation.skill_name,
      summary: observation.summary,
      related_files: observation.related_files ?? [],
      facts: observation.facts ?? {},
      tool_calls: observation.tool_calls ?? [],
      created_at: observation.created_at ?? '',
    };
    await this._appendLine(sessionId, obs);
    await this._touchSidecar(sessionId);
    return obs;
  }

  async getSkillObs(
    sessionId: string,
    limit: number = 10,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const obsLines = lines.filter((l) => l.type === 'skill_obs');
    const recent = obsLines.slice(-Math.max(1, limit));
    return recent.map((o) => ({
      observation_id: o.observation_id ?? '',
      thread_id: sessionId,
      turn_id: o.turn_id,
      skill_name: o.skill_name ?? '',
      summary_redacted: o.summary ?? '',
      related_files: o.related_files ?? [],
      created_at: o.created_at || o.timestamp || '',
      metadata: { facts: o.facts ?? {}, tool_calls: o.tool_calls ?? [] },
    }));
  }

  // ── Research observations ─────────────────────────────────────────

  async appendResearchObs(
    sessionId: string,
    observation: {
      query: string;
      sources?: Array<Record<string, unknown>>;
      evidence?: Array<Record<string, unknown>>;
      answer_summary: string;
      confidence?: number;
      search_tasks?: Array<Record<string, unknown>>;
      remaining_questions?: string[];
      created_at?: string;
    },
    turnId?: string | null,
  ): Promise<Record<string, unknown>> {
    const obs: Record<string, unknown> = {
      type: 'research_obs',
      observation_id: `researchobs_${crypto.randomUUID().slice(0, 12)}`,
      turn_id: turnId ?? null,
      query: observation.query,
      sources: observation.sources ?? [],
      evidence: observation.evidence ?? [],
      answer_summary: observation.answer_summary,
      confidence: observation.confidence ?? 0,
      search_tasks: observation.search_tasks ?? [],
      remaining_questions: observation.remaining_questions ?? [],
      created_at: observation.created_at ?? '',
    };
    await this._appendLine(sessionId, obs);
    await this._touchSidecar(sessionId);
    return obs;
  }

  async getResearchObs(
    sessionId: string,
    limit: number = 10,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const obsLines = lines.filter((l) => l.type === 'research_obs');
    const recent = obsLines.slice(-Math.max(1, limit));
    return recent.map((o) => ({
      observation_id: o.observation_id ?? '',
      thread_id: sessionId,
      turn_id: o.turn_id,
      query_redacted: o.query ?? '',
      sources_redacted: o.sources ?? [],
      evidence_redacted: o.evidence ?? [],
      answer_summary_redacted: o.answer_summary ?? '',
      confidence: Number(o.confidence ?? 0),
      created_at: o.created_at || o.timestamp || '',
      metadata: {
        search_tasks: o.search_tasks ?? [],
        remaining_questions: o.remaining_questions ?? [],
      },
    }));
  }

  // ── Approval audits ───────────────────────────────────────────────

  async appendApproval(
    sessionId: string,
    approval: Record<string, unknown>,
    turnId?: string | null,
  ): Promise<Record<string, unknown>> {
    const entry: Record<string, unknown> = {
      type: 'approval',
      approval_id: String(approval.approval_id ?? `approval_${crypto.randomUUID().slice(0, 12)}`),
      turn_id: turnId ?? null,
      tool_name: String(approval.tool_name ?? ''),
      arguments_preview: approval.arguments_preview ?? approval.arguments_preview_redacted ?? {},
      status: String(approval.status ?? approval.decision ?? ''),
      decision: approval.decision ?? null,
      reason: approval.reason ?? null,
      created_at: String(approval.created_at ?? utcNow()),
      decided_at: approval.decided_at ?? null,
    };
    await this._appendLine(sessionId, entry);
    await this._touchSidecar(sessionId);
    return entry;
  }

  async getApprovals(
    sessionId: string,
    limit: number = 20,
  ): Promise<Array<Record<string, unknown>>> {
    const lines = await this._ensureLoaded(sessionId);
    const appLines = lines.filter((l) => l.type === 'approval');
    const recent = appLines.slice(-Math.max(1, limit));
    return recent.map((a) => ({
      approval_id: a.approval_id ?? '',
      thread_id: sessionId,
      turn_id: a.turn_id,
      tool_name: a.tool_name ?? '',
      arguments_preview_redacted: a.arguments_preview ?? {},
      status: a.status ?? '',
      decision: a.decision,
      reason_redacted: a.reason,
      created_at: a.created_at ?? '',
      decided_at: a.decided_at,
    }));
  }

  // ── Mutable state (sidecar) ───────────────────────────────────────

  async saveActiveTask(
    sessionId: string,
    activeTask: {
      user_goal: string;
      related_files?: string[];
      remaining_work?: string[];
      risks?: string[];
    } | null,
  ): Promise<void> {
    if (!activeTask) return;
    const data = await this._loadSidecar(sessionId) as unknown as Record<string, unknown>;
    data.active_task = {
      summary: activeTask.user_goal,
      related_files: activeTask.related_files ?? [],
      remaining_work: activeTask.remaining_work ?? [],
      metadata: { ...activeTask },
    };
    await this._saveSidecar(sessionId);
  }

  async getActiveTask(sessionId: string): Promise<Record<string, unknown> | null> {
    const data = (await this._loadSidecar(sessionId)) as unknown as Record<string, unknown>;
    const task = data.active_task as Record<string, unknown> | undefined;
    if (!task) return null;
    return {
      thread_id: sessionId,
      summary_redacted: task.summary ?? '',
      related_files: task.related_files ?? [],
      remaining_work: task.remaining_work ?? [],
      updated_at: data.updated_at ?? '',
      metadata: task.metadata ?? {},
    };
  }

  async saveHandoff(
    sessionId: string,
    handoff: {
      current_state: string;
      risks?: string[];
      user_goal?: string;
      completed_work?: string[];
      remaining_work?: string[];
      context_to_keep?: string[];
    } | null,
  ): Promise<void> {
    if (!handoff) return;
    const data = await this._loadSidecar(sessionId) as unknown as Record<string, unknown>;
    data.handoff_summary = {
      summary: handoff.current_state,
      risks: handoff.risks ?? [],
      metadata: { ...handoff },
    };
    await this._saveSidecar(sessionId);
  }

  async getHandoff(sessionId: string): Promise<Record<string, unknown> | null> {
    const data = (await this._loadSidecar(sessionId)) as unknown as Record<string, unknown>;
    const hs = data.handoff_summary as Record<string, unknown> | undefined;
    if (!hs) return null;
    return {
      thread_id: sessionId,
      summary_redacted: hs.summary ?? '',
      risks: hs.risks ?? [],
      updated_at: data.updated_at ?? '',
      metadata: hs.metadata ?? {},
    };
  }

  async saveProjectFacts(
    sessionId: string,
    projectId: string | null,
    facts: Record<string, unknown> | null,
  ): Promise<void> {
    if (!projectId || !facts) return;
    const data = (await this._loadSidecar(sessionId)) as unknown as Record<string, unknown>;
    const projects = (data.projects ?? {}) as Record<string, unknown>;
    projects[projectId] = {
      recent_files: (facts.recent_files as unknown[]) ?? [],
      recent_sources: (facts.recent_sources as unknown[]) ?? [],
    };
    data.projects = projects;
    await this._saveSidecar(sessionId);
  }

  async getProjectFacts(
    sessionId: string,
    projectId?: string | null,
  ): Promise<Record<string, unknown> | null> {
    if (!projectId) return null;
    const data = (await this._loadSidecar(sessionId)) as unknown as Record<string, unknown>;
    const projects = (data.projects ?? {}) as Record<string, unknown>;
    const proj = projects[projectId] as Record<string, unknown> | undefined;
    if (!proj) return null;
    const facts = [...(proj.recent_files as unknown[] ?? []), ...(proj.recent_sources as unknown[] ?? [])];
    return {
      project_id: projectId,
      facts_redacted: facts,
      updated_at: data.updated_at ?? '',
    };
  }

  // ── Task plans ────────────────────────────────────────────────────

  async saveTaskPlan(
    planId: string,
    sessionId: string,
    goal: string,
    stepsJson: string,
    status: string = 'active',
    metadata?: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const plan: Record<string, unknown> = {
      type: 'task_plan',
      plan_id: planId,
      session_id: sessionId,
      goal,
      steps: stepsJson,
      status,
      metadata: JSON.stringify(metadata ?? {}),
    };
    await this._appendLine(sessionId, plan);
    return {
      plan_id: planId,
      session_id: sessionId,
      goal,
      steps_json: stepsJson,
      status,
      created_at: plan.timestamp ?? '',
      updated_at: plan.timestamp ?? '',
      metadata_json: plan.metadata,
    };
  }

  async loadTaskPlan(planId: string): Promise<Record<string, unknown> | null> {
    for (const sid of this._cache.keys()) {
      const lines = await this._ensureLoaded(sid);
      for (let i = lines.length - 1; i >= 0; i--) {
        const l = lines[i];
        if (l.type === 'task_plan' && l.plan_id === planId) {
          return {
            plan_id: l.plan_id ?? '',
            session_id: l.session_id ?? '',
            goal: l.goal ?? '',
            steps_json: l.steps ?? '[]',
            status: l.status ?? 'active',
            created_at: l.timestamp ?? '',
            updated_at: l.timestamp ?? '',
            metadata_json: l.metadata ?? '{}',
          };
        }
      }
    }
    return null;
  }

  async loadActivePlan(sessionId: string): Promise<Record<string, unknown> | null> {
    const lines = await this._ensureLoaded(sessionId);
    for (let i = lines.length - 1; i >= 0; i--) {
      const l = lines[i];
      if (l.type === 'task_plan' && l.status === 'active') {
        return {
          plan_id: l.plan_id ?? '',
          session_id: l.session_id ?? '',
          goal: l.goal ?? '',
          steps_json: l.steps ?? '[]',
          status: l.status ?? 'active',
          created_at: l.timestamp ?? '',
          updated_at: l.timestamp ?? '',
          metadata_json: l.metadata ?? '{}',
        };
      }
    }
    return null;
  }

  async listTaskPlans(
    sessionId?: string | null,
    limit: number = 20,
  ): Promise<Array<Record<string, unknown>>> {
    let plans: SessionRecord[] = [];
    if (sessionId) {
      const lines = await this._ensureLoaded(sessionId);
      plans = lines.filter((l) => l.type === 'task_plan');
    } else {
      for (const sid of this._cache.keys()) {
        const lines = await this._ensureLoaded(sid);
        plans.push(...lines.filter((l) => l.type === 'task_plan'));
      }
    }
    plans.sort((a, b) => String(b.timestamp ?? '').localeCompare(String(a.timestamp ?? '')));
    return plans.slice(0, Math.max(1, limit)).map((p) => ({
      plan_id: p.plan_id ?? '',
      session_id: p.session_id ?? '',
      goal: p.goal ?? '',
      steps_json: p.steps ?? '[]',
      status: p.status ?? 'active',
      created_at: p.timestamp ?? '',
      updated_at: p.timestamp ?? '',
      metadata_json: p.metadata ?? '{}',
    }));
  }

  async updateTaskPlan(
    planId: string,
    opts?: { stepsJson?: string; status?: string },
  ): Promise<Record<string, unknown> | null> {
    const record = await this.loadTaskPlan(planId);
    if (!record) return null;
    const sessionId = String(record.session_id ?? '');
    const newSteps = opts?.stepsJson ?? String(record.steps_json ?? '[]');
    const newStatus = opts?.status ?? String(record.status ?? 'active');
    const plan: Record<string, unknown> = {
      type: 'task_plan',
      plan_id: planId,
      session_id: sessionId,
      goal: record.goal ?? '',
      steps: newSteps,
      status: newStatus,
      metadata: record.metadata_json ?? '{}',
    };
    await this._appendLine(sessionId, plan);
    record.steps_json = newSteps;
    record.status = newStatus;
    record.updated_at = plan.timestamp ?? '';
    return record;
  }

  // ── Final answer ──────────────────────────────────────────────────

  async saveFinalAnswer(sessionId: string, turnId: string, answer: string): Promise<void> {
    await this.appendMessage(sessionId, 'assistant', answer, {
      turnId,
      metadata: { kind: 'final_answer' },
    });
    await this._appendLine(sessionId, {
      type: 'turn',
      event: 'final_answer',
      turn_id: turnId,
      output_summary: answer.slice(0, 1200),
    });
    await this._touchSidecar(sessionId);
  }

  // ── Backward-compat aliases ───────────────────────────────────────

  async appendTurn(
    sessionId: string,
    agentResult: Record<string, unknown>,
    _userInput?: string | null,
  ): Promise<Record<string, unknown>> {
    return this.endTurn(sessionId, {
      turnId: agentResult.turnId as string,
      finalAnswer: agentResult.finalAnswer as string,
      summary: agentResult.summary as Record<string, unknown>,
      outputType: agentResult.outputType as string,
      stopReason: agentResult.stopReason as string,
      skillsUsed: agentResult.skillsUsed as string[],
      toolCalls: agentResult.toolCalls as unknown[],
      events: agentResult.events as unknown[],
      status: agentResult.status as string,
    });
  }

  async appendSkillObservation(
    sessionId: string,
    observation: Record<string, unknown>,
    turnId?: string | null,
  ): Promise<Record<string, unknown>> {
    return this.appendSkillObs(sessionId, {
      skill_name: String(observation.skill_name ?? ''),
      summary: String(observation.summary ?? ''),
      related_files: observation.related_files as string[],
      facts: observation.facts as Record<string, unknown>,
      tool_calls: observation.tool_calls as string[],
      created_at: observation.created_at as string,
    }, turnId);
  }

  async appendResearchObservation(
    sessionId: string,
    observation: Record<string, unknown>,
    turnId?: string | null,
  ): Promise<Record<string, unknown>> {
    return this.appendResearchObs(sessionId, {
      query: String(observation.query ?? ''),
      sources: observation.sources as Array<Record<string, unknown>>,
      evidence: observation.evidence as Array<Record<string, unknown>>,
      answer_summary: String(observation.answer_summary ?? ''),
      confidence: Number(observation.confidence ?? 0),
      search_tasks: observation.search_tasks as Array<Record<string, unknown>>,
      remaining_questions: observation.remaining_questions as string[],
    }, turnId);
  }

  async saveHandoffSummary(sessionId: string, handoff: Record<string, unknown>): Promise<void> {
    return this.saveHandoff(sessionId, {
      current_state: String(handoff.current_state ?? ''),
      risks: handoff.risks as string[],
      user_goal: handoff.user_goal as string,
      completed_work: handoff.completed_work as string[],
      remaining_work: handoff.remaining_work as string[],
    });
  }

  async getSkillObservations(sessionId: string, limit: number = 10): Promise<Array<Record<string, unknown>>> {
    return this.getSkillObs(sessionId, limit);
  }

  async getResearchObservations(sessionId: string, limit: number = 10): Promise<Array<Record<string, unknown>>> {
    return this.getResearchObs(sessionId, limit);
  }

  async getHandoffSummary(sessionId: string): Promise<Record<string, unknown> | null> {
    return this.getHandoff(sessionId);
  }

  async appendApprovalAudit(
    sessionId: string,
    turnId: string | null,
    approval: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.appendApproval(sessionId, approval, turnId);
  }

  async getApprovalAudits(sessionId: string, limit: number = 20): Promise<Array<Record<string, unknown>>> {
    return this.getApprovals(sessionId, limit);
  }
}
