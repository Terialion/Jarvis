import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildRepoMap, repoMapTool } from '../builtin/repo-map.js';

let root: string;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'jarvis-repo-map-'));
  mkdirSync(join(root, 'src'), { recursive: true });
  mkdirSync(join(root, 'src', 'core'), { recursive: true });
  mkdirSync(join(root, 'src', 'lib'), { recursive: true });
  mkdirSync(join(root, 'node_modules', 'ignored'), { recursive: true });
  writeFileSync(join(root, 'package.json'), JSON.stringify({ name: 'fixture-app', main: 'src/index.ts' }, null, 2));
  writeFileSync(join(root, 'src', 'index.ts'), [
    'import { add } from "./lib/math";',
    'import zod from "zod";',
    'import { api } from "@/core/api";',
    'export interface User { id: string }',
    'export class AppService {}',
    'export function startApp() { return Boolean(api) && zod !== undefined; }',
    'export const version = "1.0.0";',
  ].join('\n'));
  writeFileSync(join(root, 'src', 'core', 'api.ts'), 'export const api = {};');
  writeFileSync(join(root, 'src', 'lib', 'math.ts'), [
    'import { join } from "node:path";',
    'type Count = number;',
    'function add(a: number, b: number) { return a + b; }',
    'export { add };',
  ].join('\n'));
  writeFileSync(join(root, 'node_modules', 'ignored', 'bad.ts'), 'export function ignored() {}');
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

describe('repo_map', () => {
  it('builds a compact project map with package, entries, files, symbols, imports, and dependency groups', async () => {
    const map = await buildRepoMap({ root, maxFiles: 20, maxSymbols: 20 });

    expect(map.root).toBe(root.replace(/\\/g, '/'));
    expect(map.package?.name).toBe('fixture-app');
    expect(map.entries).toContain('package.json');
    expect(map.entries).toContain('src/index.ts');
    expect(map.files.map((file) => file.path)).toContain('src/index.ts');
    expect(map.files.map((file) => file.path)).not.toContain('node_modules/ignored/bad.ts');
    expect(map.imports.map((imp) => `${imp.kind}:${imp.target}`)).toEqual(
      expect.arrayContaining([
        'relative:./lib/math',
        'external:zod',
        'internal:@/core/api',
        'external:node:path',
      ]),
    );
    expect(map.summary.importsIndexed).toBeGreaterThanOrEqual(4);
    expect(map.importGroups.relative).toMatchObject({
      count: 1,
      targets: ['./lib/math'],
      files: ['src/index.ts'],
    });
    expect(map.importGroups.internal).toMatchObject({
      count: 1,
      targets: ['@/core/api'],
      files: ['src/index.ts'],
    });
    expect(map.importGroups.external.targets).toEqual(['node:path', 'zod']);
    expect(map.symbols.map((symbol) => `${symbol.kind}:${symbol.name}`)).toEqual(
      expect.arrayContaining([
        'interface:User',
        'class:AppService',
        'function:startApp',
        'const:version',
        'type:Count',
        'function:add',
      ]),
    );
  });

  it('returns JSON from the tool handler', async () => {
    const result = await repoMapTool.handler({ path: root, max_files: 20, max_symbols: 20 }, {});
    const parsed = JSON.parse(result);

    expect(parsed.package.name).toBe('fixture-app');
    expect(parsed.summary.filesScanned).toBeGreaterThan(0);
    expect(parsed.summary.importsIndexed).toBeGreaterThan(0);
    expect(parsed.imports.some((imp: { target: string }) => imp.target === './lib/math')).toBe(true);
    expect(parsed.importGroups.external.targets).toEqual(['node:path', 'zod']);
    expect(parsed.symbols.some((symbol: { name: string }) => symbol.name === 'startApp')).toBe(true);
  });
});