import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { SessionStore } from '@jarvis/store';
import { MarkdownMemoryStore } from '@jarvis/store';
import type { MemoryEntry } from '@jarvis/store';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';

describe('E2E: Store (session + memory)', () => {
  const tmpDir = path.join(os.tmpdir(), `jarvis-e2e-store-${Date.now()}`);
  const sessionId = `e2e-test-${Date.now()}`;

  afterAll(() => {
    if (fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('SessionStore: creates session and writes sidecar', async () => {
    const store = new SessionStore(tmpDir);

    await store.createSession(sessionId, { title: 'E2E Test Session' });

    const exists = await store.sessionExists(sessionId);
    expect(exists).toBe(true);

    const sidecar = await store.getSidecar(sessionId);
    expect(sidecar.title).toBe('E2E Test Session');
  });

  it('SessionStore: appends records and reads them back', async () => {
    const store = new SessionStore(tmpDir);

    await store.createSession(sessionId);
    await store.appendRecord(sessionId, { type: 'message', role: 'user', content: 'hello' });
    await store.appendRecord(sessionId, { type: 'message', role: 'assistant', content: 'hi there' });

    const records = await store.getRecords(sessionId);
    expect(records.length).toBe(2);
    expect(records[0].type).toBe('message');
    expect(records[1].type).toBe('message');
  });

  it('SessionStore: filters records by type', async () => {
    const store = new SessionStore(tmpDir);
    const sid = `${sessionId}-filter`;

    await store.createSession(sid);
    await store.appendRecord(sid, { type: 'turn', event: 'start', turn_id: 't1' });
    await store.appendRecord(sid, { type: 'message', role: 'user', content: 'test' });
    await store.appendRecord(sid, { type: 'turn', event: 'end', turn_id: 't1' });

    const turns = await store.getRecords(sid, { type: 'turn' });
    expect(turns.length).toBe(2);
  });

  it('SessionStore: lists sessions', async () => {
    const store = new SessionStore(tmpDir);
    const sessions = await store.listSessions();
    expect(sessions.length).toBeGreaterThanOrEqual(2);
  });

  it('MarkdownMemoryStore: writes and reads entries', async () => {
    const memoryDir = path.join(tmpDir, 'memory');
    const store = new MarkdownMemoryStore(memoryDir);

    const entry: MemoryEntry = {
      name: 'test-memory',
      description: 'E2E test memory entry',
      memoryType: 'project',
      content: 'This is test memory content for E2E testing.',
    };

    const writtenPath = await store.write(entry);
    expect(fs.existsSync(writtenPath)).toBe(true);

    const loaded = await store.loadAll();
    const found = loaded.find((e) => e.name === 'test-memory');
    expect(found).toBeDefined();
    expect(found!.content).toBe('This is test memory content for E2E testing.');
  });

  it('MarkdownMemoryStore: creates MEMORY.md index', async () => {
    const memoryDir = path.join(tmpDir, 'memory2');
    const store = new MarkdownMemoryStore(memoryDir);

    await store.write({
      name: 'indexed-entry',
      description: 'Should appear in index',
      memoryType: 'reference',
      content: 'Indexed content.',
    });

    const indexPath = path.join(memoryDir, 'MEMORY.md');
    expect(fs.existsSync(indexPath)).toBe(true);
    const indexContent = fs.readFileSync(indexPath, 'utf-8');
    expect(indexContent).toContain('indexed-entry');
  });
});
