import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { randomUUID } from 'node:crypto';
import {
  MarkdownMemoryStore,
  type MemoryEntry,
} from '../memory.js';

// ============================================================================
// Helpers
// ============================================================================

let testDir: string;

beforeEach(async () => {
  testDir = path.join(os.tmpdir(), `jarvis-memory-test-${randomUUID()}`);
  await fs.mkdir(testDir, { recursive: true });
});

afterEach(async () => {
  await fs.rm(testDir, { recursive: true, force: true }).catch(() => {});
});

function createStore(): MarkdownMemoryStore {
  return new MarkdownMemoryStore(testDir);
}

function makeEntry(overrides?: Partial<MemoryEntry>): MemoryEntry {
  return {
    name: `Test Entry ${randomUUID()}`,
    description: 'A test memory entry',
    memoryType: 'project',
    content: 'This is the body content of the test entry.',
    ...overrides,
  };
}

// ============================================================================
// MarkdownMemoryStore tests
// ============================================================================

describe('MarkdownMemoryStore', () => {
  // ── loadAll ────────────────────────────────────────────────────────

  describe('loadAll', () => {
    it('loads entries from .md files', async () => {
      const store = createStore();
      const entry = makeEntry();
      await store.write(entry);

      const entries = await store.loadAll();
      expect(entries).toHaveLength(1);
      expect(entries[0].name).toBe(entry.name);
      expect(entries[0].description).toBe(entry.description);
      expect(entries[0].memoryType).toBe(entry.memoryType);
      expect(entries[0].content).toBe(entry.content);
    });

    it('returns empty array for empty directory', async () => {
      const store = createStore();
      const entries = await store.loadAll();
      expect(entries).toEqual([]);
    });

    it('skips MEMORY.md and index.md files', async () => {
      const store = createStore();
      // Create a regular entry
      const entry = makeEntry();
      await store.write(entry);

      // MEMORY.md is auto-created, but also create an index.md
      await fs.writeFile(
        path.join(testDir, 'index.md'),
        '---\nname: should-be-ignored\ndescription: ignored\ntype: project\n---\n\nBody',
        'utf-8',
      );

      const entries = await store.loadAll();
      expect(entries).toHaveLength(1);
      expect(entries[0].name).toBe(entry.name);
    });

    it('skips malformed entries', async () => {
      const store = createStore();
      // Write a file with invalid frontmatter
      await fs.writeFile(
        path.join(testDir, 'bad.md'),
        'No frontmatter here, just body',
        'utf-8',
      );
      // Write a file with frontmatter but no name
      await fs.writeFile(
        path.join(testDir, 'noname.md'),
        '---\ndescription: no name field\ntype: project\n---\n\nBody',
        'utf-8',
      );

      const entries = await store.loadAll();
      // Neither should be loaded — both fail validation (meta.name && body)
      const names = entries.map((e) => e.name);
      expect(names).not.toContain('bad');
    });
  });

  // ── write ─────────────────────────────────────────────────────────

  describe('write', () => {
    it('writes an entry with frontmatter', async () => {
      const store = createStore();
      const entry = makeEntry({
        name: 'My Memory',
        description: 'Important notes',
        memoryType: 'user',
        content: 'This is the body.\nMultiline content.',
      });

      const filePath = await store.write(entry);

      // Read back the raw file
      const raw = await fs.readFile(filePath, 'utf-8');
      expect(raw).toContain('---');
      expect(raw).toContain('name: My Memory');
      expect(raw).toContain('description: Important notes');
      expect(raw).toContain('type: user');
      expect(raw).toContain('This is the body.\nMultiline content.');
    });

    it('updates MEMORY.md index with the entry link', async () => {
      const store = createStore();
      const entry = makeEntry({
        name: 'Indexed Entry',
        description: 'Should appear in index',
      });

      await store.write(entry);
      expect(store.indexPath).toBeTruthy();

      const indexContent = await fs.readFile(store.indexPath, 'utf-8');
      expect(indexContent).toContain('[Indexed Entry]');
      expect(indexContent).toContain('Should appear in index');
    });

    it('updates an existing entry in the index', async () => {
      const store = createStore();
      const entry = makeEntry({
        name: 'Update Me',
        description: 'First version',
      });

      await store.write(entry);

      // Update same entry
      entry.description = 'Updated version';
      await store.write(entry);

      const indexContent = await fs.readFile(store.indexPath, 'utf-8');
      expect(indexContent).toContain('Updated version');
      // Should only have one entry (not two)
      const matchCount = (indexContent.match(/\(.*\.md\)/g) || []).length;
      expect(matchCount).toBe(1);
    });

    it('sanitizes filenames correctly', async () => {
      const store = createStore();
      const entry = makeEntry({
        name: 'Entry with special/chars: and space',
      });

      const filePath = await store.write(entry);
      const fileName = path.basename(filePath);
      // No slashes, colons, or spaces in filename
      expect(fileName).not.toContain('/');
      expect(fileName).not.toContain('\\');
      expect(fileName).not.toContain(':');
      expect(fileName).not.toContain(' ');
    });
  });

  // ── delete ────────────────────────────────────────────────────────

  describe('delete', () => {
    it('deletes the entry file', async () => {
      const store = createStore();
      const entry = makeEntry({ name: 'Delete Me' });
      await store.write(entry);

      // Verify it exists
      let entries = await store.loadAll();
      expect(entries).toHaveLength(1);

      await store.delete('Delete Me');

      entries = await store.loadAll();
      expect(entries).toHaveLength(0);
    });

    it('removes entry from MEMORY.md index', async () => {
      const store = createStore();
      const entry = makeEntry({ name: 'Remove From Index' });
      await store.write(entry);

      await store.delete('Remove From Index');

      const indexContent = await fs.readFile(store.indexPath, 'utf-8');
      expect(indexContent).not.toContain('Remove From Index');
    });

    it('does not throw for non-existent entry', async () => {
      const store = createStore();
      await expect(store.delete('nonexistent')).resolves.not.toThrow();
    });
  });

  // ── search ────────────────────────────────────────────────────────

  describe('search', () => {
    it('finds entries by name substring', async () => {
      const store = createStore();
      await store.write(makeEntry({ name: 'Alpha Project', content: 'AAA' }));
      await store.write(makeEntry({ name: 'Beta Task', content: 'BBB' }));

      const results = await store.search('Alpha');
      expect(results).toHaveLength(1);
      expect(results[0].name).toBe('Alpha Project');
    });

    it('finds entries by content substring', async () => {
      const store = createStore();
      await store.write(
        makeEntry({ name: 'Entry A', content: 'Unique content about bananas' }),
      );
      await store.write(
        makeEntry({ name: 'Entry B', content: 'Something about apples' }),
      );

      const results = await store.search('bananas');
      expect(results).toHaveLength(1);
      expect(results[0].name).toBe('Entry A');
    });

    it('finds entries by description', async () => {
      const store = createStore();
      await store.write(
        makeEntry({
          name: 'Special',
          description: 'Contains the keyword',
          content: 'Body',
        }),
      );

      const results = await store.search('keyword');
      expect(results).toHaveLength(1);
      expect(results[0].name).toBe('Special');
    });

    it('performs case-insensitive search', async () => {
      const store = createStore();
      await store.write(
        makeEntry({ name: 'UPPERCASE ENTRY', content: 'all caps' }),
      );

      const results = await store.search('uppercase');
      expect(results).toHaveLength(1);
    });

    it('requires all terms to match (AND semantics)', async () => {
      const store = createStore();
      await store.write(
        makeEntry({ name: 'Full Match', content: 'hello world' }),
      );
      await store.write(
        makeEntry({ name: 'Partial', content: 'hello' }),
      );

      const results = await store.search('hello world');
      expect(results).toHaveLength(1);
      expect(results[0].name).toBe('Full Match');
    });

    it('returns empty array for empty query', async () => {
      const store = createStore();
      await store.write(makeEntry({ name: 'Test', content: 'content' }));

      const results = await store.search('');
      expect(results).toEqual([]);
    });
  });

  // ── sanitizeName ──────────────────────────────────────────────────

  describe('sanitizeName', () => {
    it('replaces slashes with underscores', () => {
      const store = createStore();
      expect(store.sanitizeName('foo/bar/baz')).toBe('foo_bar_baz');
    });

    it('replaces backslashes with underscores', () => {
      const store = createStore();
      expect(store.sanitizeName('foo\\bar')).toBe('foo_bar');
    });

    it('replaces colons with underscores', () => {
      const store = createStore();
      expect(store.sanitizeName('key:value')).toBe('key_value');
    });

    it('replaces spaces with underscores', () => {
      const store = createStore();
      expect(store.sanitizeName('hello world')).toBe('hello_world');
    });
  });

  // ── static parseFrontmatter / formatFrontmatter ───────────────────

  describe('parseFrontmatter (static)', () => {
    it('parses valid frontmatter', () => {
      const text = [
        '---',
        'name: test-entry',
        'description: A test',
        'type: project',
        '---',
        '',
        'This is the body.',
      ].join('\n');

      const { meta, body } = MarkdownMemoryStore.parseFrontmatter(text);
      expect(meta.name).toBe('test-entry');
      expect(meta.description).toBe('A test');
      expect(meta.type).toBe('project');
      expect(body).toBe('This is the body.');
    });

    it('returns empty meta for text without frontmatter', () => {
      const { meta, body } =
        MarkdownMemoryStore.parseFrontmatter('Just plain text');
      expect(meta).toEqual({});
      expect(body).toBe('Just plain text');
    });

    it('returns empty meta for empty string', () => {
      const { meta, body } = MarkdownMemoryStore.parseFrontmatter('');
      expect(meta).toEqual({});
    });
  });

  describe('formatFrontmatter (static)', () => {
    it('formats metadata and body into markdown', () => {
      const result = MarkdownMemoryStore.formatFrontmatter(
        { name: 'test', description: 'desc', type: 'user' },
        'Hello world',
      );

      expect(result).toContain('---');
      expect(result).toContain('name: test');
      expect(result).toContain('description: desc');
      expect(result).toContain('type: user');
      expect(result).toContain('Hello world');
      expect(result.endsWith('\n')).toBe(true);
    });

    it('round-trips: format then parse yields same data', () => {
      const meta = { name: 'rt', description: 'round trip', type: 'reference' as const };
      const body = 'Body content\nSecond line';
      const formatted = MarkdownMemoryStore.formatFrontmatter(meta, body);
      const { meta: parsedMeta, body: parsedBody } =
        MarkdownMemoryStore.parseFrontmatter(formatted);

      expect(parsedMeta.name).toBe(meta.name);
      expect(parsedMeta.description).toBe(meta.description);
      expect(parsedMeta.type).toBe(meta.type);
      expect(parsedBody).toBe(body);
    });
  });

  // ── Memory type validation ────────────────────────────────────────

  describe('memoryType', () => {
    it('supports all memory types', async () => {
      const store = createStore();

      const types: MemoryEntry['memoryType'][] = [
        'user',
        'feedback',
        'project',
        'reference',
      ];

      for (const t of types) {
        await store.write(makeEntry({ name: `Type-${t}`, memoryType: t }));
      }

      const entries = await store.loadAll();
      const loadedTypes = entries.map((e) => e.memoryType);
      for (const t of types) {
        expect(loadedTypes).toContain(t);
      }
    });
  });
});
