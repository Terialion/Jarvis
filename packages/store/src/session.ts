// ============================================================================
// JSONL-based session store — append-only transcripts + sidecar JSON
// ============================================================================

import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as os from 'node:os';
import { randomUUID } from 'node:crypto';

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
    | 'task_plan';
  timestamp?: string; // ISO-8601 UTC, auto-set on write if missing
  [key: string]: unknown;
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

  /** Create a new session: JSONL file + sidecar JSON. */
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
    // Touch the JSONL file to create it
    await this._appendLine(sessionId, {
      type: 'turn',
      event: 'start',
      turn_id: `session_${randomUUID()}`,
      status: 'created',
    });
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
}
