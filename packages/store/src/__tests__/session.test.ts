import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { randomUUID } from 'node:crypto';
import { SessionStore, type SessionRecord, type SessionSidecar } from '../session.js';

// ============================================================================
// Helpers
// ============================================================================

let testDir: string;

beforeEach(async () => {
  testDir = path.join(os.tmpdir(), `jarvis-store-test-${randomUUID()}`);
  await fs.mkdir(testDir, { recursive: true });
});

afterEach(async () => {
  await fs.rm(testDir, { recursive: true, force: true }).catch(() => {});
});

function createStore(): SessionStore {
  return new SessionStore(testDir);
}

// ============================================================================
// SessionStore tests
// ============================================================================

describe('SessionStore', () => {
  // ── createSession ──────────────────────────────────────────────────

  describe('createSession', () => {
    it('creates a sidecar JSON for the session', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      expect(await store.sessionExists(sid)).toBe(true);

      // Verify sidecar exists
      const sidecarPath = path.join(testDir, `${sid}.json`);
      const sidecar = JSON.parse(await fs.readFile(sidecarPath, 'utf-8'));
      expect(sidecar.session_id).toBe(sid);
      expect(sidecar.title).toBeNull();
      expect(sidecar.created_at).toBeTruthy();
      expect(sidecar.updated_at).toBeTruthy();
    });

    it('accepts custom metadata', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid, {
        title: 'My Test Session',
        project_id: 'proj-123',
        cwd: '/home/user/project',
      });

      const sidecar = await store.getSidecar(sid);
      expect(sidecar.title).toBe('My Test Session');
      expect(sidecar.project_id).toBe('proj-123');
      expect(sidecar.cwd).toBe('/home/user/project');
    });
  });

  // ── appendRecord ───────────────────────────────────────────────────

  describe('appendRecord', () => {
    it('appends a record to the JSONL file', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      await store.appendRecord(sid, {
        type: 'message',
        role: 'user',
        content: 'Hello, world!',
      } as SessionRecord);

      const records = await store.getRecords(sid);
      // Should have: turn:start (from createSession) + the message
      const messages = records.filter((r) => r.type === 'message');
      expect(messages).toHaveLength(1);
      expect(messages[0].role).toBe('user');
      expect(messages[0].content).toBe('Hello, world!');
    });

    it('auto-stamps timestamp if missing', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      // Append record without timestamp
      await store.appendRecord(sid, {
        type: 'message',
        role: 'user',
        content: 'No timestamp',
      } as SessionRecord);

      const records = await store.getRecords(sid);
      const msg = records.find((r) => r.type === 'message')!;
      expect(msg.timestamp).toBeTruthy();
      // Should be valid ISO-8601
      expect(new Date(msg.timestamp!).toISOString()).toBeTruthy();
    });

    it('preserves existing timestamp', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      const customTs = '2024-01-15T10:30:00.000Z';
      await store.appendRecord(sid, {
        type: 'message',
        role: 'user',
        content: 'Custom timestamp',
        timestamp: customTs,
      });

      const records = await store.getRecords(sid);
      const msg = records.find((r) => r.type === 'message')!;
      expect(msg.timestamp).toBe(customTs);
    });

    it('updates sidecar updated_at on each append', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      const sidecarBefore = await store.getSidecar(sid);
      const updatedAtBefore = sidecarBefore.updated_at;

      // Wait a tiny bit to ensure timestamp changes
      await new Promise((resolve) => setTimeout(resolve, 10));

      await store.appendRecord(sid, {
        type: 'message',
        role: 'assistant',
        content: 'Response',
      } as SessionRecord);

      const sidecarAfter = await store.getSidecar(sid);
      expect(sidecarAfter.updated_at).not.toBe(updatedAtBefore);
    });
  });

  // ── getRecords ─────────────────────────────────────────────────────

  describe('getRecords', () => {
    it('returns all records when no filter', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      await store.appendRecord(sid, { type: 'message', role: 'user', content: 'A' } as SessionRecord);
      await store.appendRecord(sid, { type: 'message', role: 'assistant', content: 'B' } as SessionRecord);
      await store.appendRecord(sid, { type: 'tool_call', tool_name: 'read', call_id: 'c1' } as SessionRecord);

      const records = await store.getRecords(sid);
      // turn:start + 3 records = 4
      expect(records.length).toBeGreaterThanOrEqual(3);
    });

    it('filters by type', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      await store.appendRecord(sid, { type: 'message', role: 'user', content: 'Hi' } as SessionRecord);
      await store.appendRecord(sid, { type: 'tool_call', tool_name: 'read', call_id: 'c1' } as SessionRecord);
      await store.appendRecord(sid, { type: 'tool_result', call_id: 'c1', ok: true } as SessionRecord);

      const messages = await store.getRecords(sid, { type: 'message' });
      expect(messages.length).toBeGreaterThanOrEqual(1);
      for (const m of messages) {
        expect(m.type).toBe('message');
      }

      const toolCalls = await store.getRecords(sid, { type: 'tool_call' });
      expect(toolCalls).toHaveLength(1);
      expect(toolCalls[0].tool_name).toBe('read');
    });

    it('returns empty array for non-existent session', async () => {
      const store = createStore();
      const records = await store.getRecords('nonexistent');
      expect(records).toEqual([]);
    });
  });

  // ── getSidecar / updateSidecar ─────────────────────────────────────

  describe('sidecar operations', () => {
    it('getSidecar returns sidecar data', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid, { title: 'Test' });

      const sidecar = await store.getSidecar(sid);
      expect(sidecar.session_id).toBe(sid);
      expect(sidecar.title).toBe('Test');
    });

    it('getSidecar returns default values for missing session', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      // Don't create — just query
      const sidecar = await store.getSidecar(sid);
      expect(sidecar.session_id).toBe(sid);
      expect(sidecar.title).toBeNull();
      expect(sidecar.created_at).toBeTruthy();
      expect(sidecar.project_id).toBeNull();
    });

    it('updateSidecar merges fields', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid, { title: 'Original' });

      await store.updateSidecar(sid, {
        title: 'Updated Title',
        cwd: '/new/cwd',
      });

      const sidecar = await store.getSidecar(sid);
      expect(sidecar.title).toBe('Updated Title');
      expect(sidecar.cwd).toBe('/new/cwd');
      // Unchanged fields preserved
      expect(sidecar.project_id).toBeNull();
    });
  });

  // ── listSessions ───────────────────────────────────────────────────

  describe('listSessions', () => {
    it('lists all created sessions', async () => {
      const store = createStore();
      const sid1 = `session_${randomUUID()}`;
      const sid2 = `session_${randomUUID()}`;

      await store.createSession(sid1);
      await store.createSession(sid2);

      const sessions = await store.listSessions();
      expect(sessions).toContain(sid1);
      expect(sessions).toContain(sid2);
    });

    it('returns empty array when no sessions exist', async () => {
      const store = createStore();
      const sessions = await store.listSessions();
      expect(sessions).toEqual([]);
    });

    it('returns sorted IDs', async () => {
      const store = createStore();
      const sid1 = 'session_bbb';
      const sid2 = 'session_aaa';

      await store.createSession(sid1);
      await store.createSession(sid2);

      const sessions = await store.listSessions();
      const idx1 = sessions.indexOf(sid1);
      const idx2 = sessions.indexOf(sid2);
      expect(idx1).toBeGreaterThan(idx2); // aaa before bbb
    });
  });

  // ── sessionExists ──────────────────────────────────────────────────

  describe('sessionExists', () => {
    it('returns true for created session', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      expect(await store.sessionExists(sid)).toBe(true);
    });

    it('returns false for non-existent session', async () => {
      const store = createStore();
      expect(await store.sessionExists('nonexistent')).toBe(false);
    });
  });

  // ── JSONL format compatibility ─────────────────────────────────────

  describe('JSONL format', () => {
    it('each line is a valid JSON object', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      await store.appendRecord(sid, {
        type: 'message',
        role: 'assistant',
        content: 'Hello',
        metadata: { key: 'value' },
      } as SessionRecord);

      const jsonlPath = path.join(testDir, `${sid}.jsonl`);
      const content = await fs.readFile(jsonlPath, 'utf-8');
      const lines = content.trim().split('\n');

      for (const line of lines) {
        const obj = JSON.parse(line);
        expect(typeof obj).toBe('object');
        expect(obj).not.toBeNull();
        expect('timestamp' in obj).toBe(true);
      }
    });

    it('handles all record types', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      const types: SessionRecord['type'][] = [
        'turn',
        'message',
        'tool_call',
        'tool_result',
        'summary',
        'skill_obs',
        'research_obs',
        'approval',
        'task_plan',
      ];

      for (const type of types) {
        await store.appendRecord(sid, { type } as SessionRecord);
      }

      const records = await store.getRecords(sid);
      for (const type of types) {
        expect(records.some((r) => r.type === type)).toBe(true);
      }
    });

    it('stores unicode content correctly', async () => {
      const store = createStore();
      const sid = `session_${randomUUID()}`;
      await store.createSession(sid);

      const content = 'Hello 世界 🌍 — em-dash and Unicode';
      await store.appendRecord(sid, {
        type: 'message',
        role: 'user',
        content,
      } as SessionRecord);

      const records = await store.getRecords(sid);
      const msg = records.find((r) => r.type === 'message')!;
      expect(msg.content).toBe(content);
    });
  });
});
