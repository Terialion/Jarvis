import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { scanFiles, type FileEntry } from '../fileScanner.js';

describe('fileScanner', () => {
  const testDir = join(process.cwd(), '.test-file-scanner');

  beforeEach(() => {
    // Create test directory structure
    mkdirSync(testDir, { recursive: true });
    mkdirSync(join(testDir, 'src'), { recursive: true });
    mkdirSync(join(testDir, 'src', 'utils'), { recursive: true });
    mkdirSync(join(testDir, 'node_modules'), { recursive: true });
    mkdirSync(join(testDir, '.git'), { recursive: true });

    writeFileSync(join(testDir, 'README.md'), '# Test');
    writeFileSync(join(testDir, 'package.json'), '{}');
    writeFileSync(join(testDir, 'src', 'index.ts'), 'export {}');
    writeFileSync(join(testDir, 'src', 'utils', 'helper.ts'), 'export {}');
    writeFileSync(join(testDir, 'src', 'utils', 'types.d.ts'), 'export {}');
    writeFileSync(join(testDir, 'node_modules', 'dep.js'), '');
  });

  afterEach(() => {
    // Cleanup
    try {
      rmSync(testDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it('should list root-level files and directories when no query', async () => {
    const entries = await scanFiles(testDir);
    const paths = entries.map((e) => e.path);

    // With no query, only depth 1 entries are shown
    expect(paths).toContain('README.md');
    expect(paths).toContain('package.json');
    expect(paths).toContain('src');
    // Nested entries should NOT be shown without query
    expect(paths).not.toContain('src/index.ts');
    expect(paths).not.toContain('src/utils');
    expect(paths).not.toContain('src/utils/helper.ts');
  });

  it('should list nested files when query is provided', async () => {
    const entries = await scanFiles(testDir, 'helper');
    const paths = entries.map((e) => e.path);

    // With query, should find nested files
    expect(paths).toContain('src/utils/helper.ts');
  });

  it('should skip ignored directories', async () => {
    const entries = await scanFiles(testDir);
    const paths = entries.map((e) => e.path);

    expect(paths).not.toContain('node_modules');
    expect(paths).not.toContain('.git');
    expect(paths).not.toContain('node_modules/dep.js');
  });

  it('should filter by query', async () => {
    const entries = await scanFiles(testDir, 'helper');
    const paths = entries.map((e) => e.path);

    expect(paths).toContain('src/utils/helper.ts');
    expect(paths).not.toContain('README.md');
  });

  it('should filter by path segment', async () => {
    const entries = await scanFiles(testDir, 'utils');
    const paths = entries.map((e) => e.path);

    expect(paths).toContain('src/utils');
    expect(paths).toContain('src/utils/helper.ts');
    expect(paths).toContain('src/utils/types.d.ts');
  });

  it('should mark directories correctly', async () => {
    const entries = await scanFiles(testDir);
    const srcEntry = entries.find((e) => e.path === 'src');
    const readmeEntry = entries.find((e) => e.path === 'README.md');

    expect(srcEntry?.isDir).toBe(true);
    expect(readmeEntry?.isDir).toBe(false);
  });

  it('should sort directories first', async () => {
    const entries = await scanFiles(testDir);

    // Find first file index
    const firstFileIdx = entries.findIndex((e) => !e.isDir);
    // All entries before first file should be directories
    for (let i = 0; i < firstFileIdx; i++) {
      expect(entries[i].isDir).toBe(true);
    }
  });

  it('should push low-priority files to end', async () => {
    const entries = await scanFiles(testDir);
    const dtsIdx = entries.findIndex((e) => e.path.endsWith('.d.ts'));
    const readmeIdx = entries.findIndex((e) => e.path === 'README.md');

    // .d.ts should come after regular files
    if (dtsIdx >= 0 && readmeIdx >= 0) {
      expect(dtsIdx).toBeGreaterThan(readmeIdx);
    }
  });

  it('should respect maxResults', async () => {
    const entries = await scanFiles(testDir, '', 3);
    expect(entries.length).toBeLessThanOrEqual(3);
  });

  it('should respect maxDepth when query is provided', async () => {
    // maxDepth is only used when there's a query
    const entries = await scanFiles(testDir, 'src', 50, 1);
    const paths = entries.map((e) => e.path);

    // With query 'src' and maxDepth 1, should include src/ and its immediate contents
    expect(paths).toContain('src');
    expect(paths).toContain('src/index.ts');
    expect(paths).toContain('src/utils');
    // But not deeper nested files (depth 2)
    expect(paths).not.toContain('src/utils/helper.ts');
    expect(paths).not.toContain('src/utils/types.d.ts');
  });

  it('should handle empty query', async () => {
    const entries = await scanFiles(testDir, '');
    expect(entries.length).toBeGreaterThan(0);
  });

  it('should handle non-existent directory gracefully', async () => {
    const entries = await scanFiles('/non/existent/path');
    expect(entries).toEqual([]);
  });
});
