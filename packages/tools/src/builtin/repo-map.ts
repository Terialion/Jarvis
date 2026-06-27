// ============================================================================
// repo_map - lightweight repository map and symbol index.
// First phase intentionally avoids tree-sitter/embeddings; it gives the agent a
// compact orientation pass before grep/read_file deep dives.
// ============================================================================

import { readdir, readFile, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

const SKIP_DIRS = new Set([
  '.git', '.hg', '.svn', 'node_modules', 'dist', 'build', 'coverage', '.next', '.turbo',
  '.cache', '__pycache__', '.venv', 'venv', 'target', 'out', '.idea', '.vscode',
]);

const SOURCE_EXTENSIONS = new Set([
  '.ts', '.tsx', '.js', '.jsx', '.mts', '.cts', '.mjs', '.cjs',
  '.py', '.rs', '.go', '.java', '.kt', '.kts', '.c', '.h', '.cpp', '.hpp',
  '.cs', '.php', '.rb', '.swift', '.scala', '.vue', '.svelte',
]);

const ENTRY_FILES = new Set([
  'package.json', 'pnpm-workspace.yaml', 'turbo.json', 'tsconfig.json', 'vite.config.ts',
  'next.config.js', 'README.md', 'readme.md', 'pyproject.toml', 'Cargo.toml', 'go.mod',
  'deno.json', 'bun.lockb', 'requirements.txt',
]);

export type RepoMapFile = {
  path: string;
  language: string;
  lines: number;
  size: number;
};

export type RepoMapSymbol = {
  name: string;
  kind: 'class' | 'function' | 'interface' | 'type' | 'const' | 'export';
  file: string;
  line: number;
};

export type RepoMapImport = {
  from: string;
  target: string;
  kind: 'external' | 'internal' | 'relative';
  file: string;
  line: number;
};

export type RepoMapImportGroup = {
  kind: RepoMapImport['kind'];
  count: number;
  targets: string[];
  files: string[];
};

export type RepoMapImportGroups = Record<RepoMapImport['kind'], RepoMapImportGroup>;

export type RepoMapResult = {
  root: string;
  package?: { name?: string; main?: string; scripts?: string[] };
  entries: string[];
  files: RepoMapFile[];
  symbols: RepoMapSymbol[];
  imports: RepoMapImport[];
  importGroups: RepoMapImportGroups;
  summary: {
    filesScanned: number;
    symbolsIndexed: number;
    importsIndexed: number;
    truncated: boolean;
  };
};

export type RepoMapOptions = {
  root?: string;
  maxFiles?: number;
  maxSymbols?: number;
  includeTests?: boolean;
};

function toPosix(path: string): string {
  return path.replace(/\\/g, '/');
}

function languageForExtension(ext: string): string {
  switch (ext) {
    case '.ts':
    case '.tsx':
    case '.mts':
    case '.cts':
      return 'typescript';
    case '.js':
    case '.jsx':
    case '.mjs':
    case '.cjs':
      return 'javascript';
    case '.py': return 'python';
    case '.rs': return 'rust';
    case '.go': return 'go';
    case '.java': return 'java';
    case '.kt':
    case '.kts': return 'kotlin';
    case '.c':
    case '.h':
    case '.cpp':
    case '.hpp': return 'cpp';
    case '.cs': return 'csharp';
    case '.php': return 'php';
    case '.rb': return 'ruby';
    case '.swift': return 'swift';
    case '.scala': return 'scala';
    case '.vue': return 'vue';
    case '.svelte': return 'svelte';
    default: return ext.replace(/^\./, '') || 'unknown';
  }
}

function isLikelyTestPath(relPath: string): boolean {
  return /(^|\/)(__tests__|test|tests|spec)(\/|$)/i.test(relPath) || /\.(test|spec)\.[cm]?[tj]sx?$/i.test(relPath);
}

async function walkSourceFiles(root: string, opts: { maxFiles: number; includeTests: boolean; signal?: AbortSignal }): Promise<string[]> {
  const files: string[] = [];

  async function walk(dir: string): Promise<void> {
    if (opts.signal?.aborted) throw new Error('Tool interrupted');
    if (files.length >= opts.maxFiles) return;

    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }

    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (files.length >= opts.maxFiles) return;
      const fullPath = join(dir, entry.name);
      const relPath = toPosix(relative(root, fullPath));
      if (entry.isDirectory()) {
        if (SKIP_DIRS.has(entry.name)) continue;
        if (entry.name.startsWith('.') && entry.name !== '.github') continue;
        await walk(fullPath);
      } else if (entry.isFile()) {
        const ext = extname(entry.name).toLowerCase();
        if (!SOURCE_EXTENSIONS.has(ext)) continue;
        if (!opts.includeTests && isLikelyTestPath(relPath)) continue;
        files.push(fullPath);
      }
    }
  }

  await walk(root);
  return files;
}

function extractSymbolsFromText(text: string, relPath: string, maxSymbols: number): RepoMapSymbol[] {
  const symbols: RepoMapSymbol[] = [];
  const lines = text.split('\n');
  const patterns: Array<[RepoMapSymbol['kind'], RegExp]> = [
    ['class', /(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)/],
    ['interface', /(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)/],
    ['type', /(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=/],
    ['function', /(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/],
    ['const', /(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=/],
    ['export', /export\s+\{\s*([^}]+)\s*\}/],
    ['function', /def\s+([A-Za-z_]\w*)\s*\(/],
    ['class', /class\s+([A-Za-z_]\w*)[(:\s]/],
  ];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';
    for (const [kind, pattern] of patterns) {
      const match = line.match(pattern);
      if (!match) continue;
      if (kind === 'export' && match[1]) {
        for (const part of match[1].split(',')) {
          const name = part.trim().split(/\s+as\s+/i)[0]?.trim();
          if (name) symbols.push({ kind, name, file: relPath, line: i + 1 });
          if (symbols.length >= maxSymbols) return symbols;
        }
      } else if (match[1]) {
        symbols.push({ kind, name: match[1], file: relPath, line: i + 1 });
      }
      if (symbols.length >= maxSymbols) return symbols;
    }
  }

  return symbols;
}

function classifyImportTarget(target: string): RepoMapImport['kind'] {
  if (target.startsWith('.')) return 'relative';
  if (target.startsWith('/') || target.startsWith('@/') || target.startsWith('~/')) return 'internal';
  return 'external';
}

function emptyImportGroup(kind: RepoMapImport['kind']): RepoMapImportGroup {
  return { kind, count: 0, targets: [], files: [] };
}

function buildImportGroups(imports: RepoMapImport[]): RepoMapImportGroups {
  const groups: RepoMapImportGroups = {
    external: emptyImportGroup('external'),
    internal: emptyImportGroup('internal'),
    relative: emptyImportGroup('relative'),
  };

  const targetSets: Record<RepoMapImport['kind'], Set<string>> = {
    external: new Set(),
    internal: new Set(),
    relative: new Set(),
  };
  const fileSets: Record<RepoMapImport['kind'], Set<string>> = {
    external: new Set(),
    internal: new Set(),
    relative: new Set(),
  };

  for (const item of imports) {
    const group = groups[item.kind];
    group.count += 1;
    targetSets[item.kind].add(item.target);
    fileSets[item.kind].add(item.file);
  }

  for (const kind of ['external', 'internal', 'relative'] as const) {
    groups[kind].targets = [...targetSets[kind]].sort();
    groups[kind].files = [...fileSets[kind]].sort();
  }

  return groups;
}
function extractImportsFromText(text: string, relPath: string, maxImports: number): RepoMapImport[] {
  const imports: RepoMapImport[] = [];
  const lines = text.split('\n');
  const patterns = [
    /\bimport\s+(?:type\s+)?(?:[^'\"]+\s+from\s+)?['\"]([^'\"]+)['\"]/, 
    /\bexport\s+(?:type\s+)?(?:[^'\"]+\s+from\s+)['\"]([^'\"]+)['\"]/, 
    /\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)/,
    /^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+/,
    /^\s*import\s+([A-Za-z_][\w.]*)/,
  ];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';
    for (const pattern of patterns) {
      const match = line.match(pattern);
      const target = match?.[1]?.trim();
      if (!target) continue;
      imports.push({
        from: relPath,
        target,
        kind: classifyImportTarget(target),
        file: relPath,
        line: i + 1,
      });
      if (imports.length >= maxImports) return imports;
      break;
    }
  }

  return imports;
}

async function readPackage(root: string): Promise<RepoMapResult['package'] | undefined> {
  const packagePath = join(root, 'package.json');
  if (!existsSync(packagePath)) return undefined;
  try {
    const data = JSON.parse(await readFile(packagePath, 'utf8')) as Record<string, unknown>;
    const scripts = data.scripts && typeof data.scripts === 'object'
      ? Object.keys(data.scripts as Record<string, unknown>).sort()
      : undefined;
    return {
      name: typeof data.name === 'string' ? data.name : undefined,
      main: typeof data.main === 'string' ? data.main : undefined,
      scripts,
    };
  } catch {
    return undefined;
  }
}

async function findEntryFiles(root: string, packageMain?: string): Promise<string[]> {
  const entries: string[] = [];
  for (const entry of ENTRY_FILES) {
    if (existsSync(join(root, entry))) entries.push(entry);
  }
  for (const candidate of ['src/index.ts', 'src/index.tsx', 'src/main.ts', 'src/main.tsx', 'src/index.js', 'src/main.js']) {
    if (existsSync(join(root, candidate))) entries.push(candidate);
  }
  if (packageMain && existsSync(join(root, packageMain))) entries.push(packageMain);
  return [...new Set(entries)].sort();
}

export async function buildRepoMap(options: RepoMapOptions = {}, context: { signal?: AbortSignal } = {}): Promise<RepoMapResult> {
  const root = resolve(options.root ?? process.cwd());
  const maxFiles = Math.max(1, Math.min(2000, options.maxFiles ?? 250));
  const maxSymbols = Math.max(1, Math.min(5000, options.maxSymbols ?? 500));
  const includeTests = options.includeTests ?? false;
  const files = await walkSourceFiles(root, { maxFiles, includeTests, signal: context.signal });
  const packageInfo = await readPackage(root);
  const entries = await findEntryFiles(root, packageInfo?.main);
  const mapFiles: RepoMapFile[] = [];
  const symbols: RepoMapSymbol[] = [];
  const imports: RepoMapImport[] = [];

  for (const file of files) {
    if (context.signal?.aborted) throw new Error('Tool interrupted');
    let text = '';
    let size = 0;
    try {
      const st = await stat(file);
      size = st.size;
      if (size > 1_000_000) continue;
      text = await readFile(file, 'utf8');
    } catch {
      continue;
    }
    const relPath = toPosix(relative(root, file));
    mapFiles.push({
      path: relPath,
      language: languageForExtension(extname(file).toLowerCase()),
      lines: text.split('\n').length,
      size,
    });
    if (symbols.length < maxSymbols) {
      symbols.push(...extractSymbolsFromText(text, relPath, maxSymbols - symbols.length));
    }
    if (imports.length < maxSymbols) {
      imports.push(...extractImportsFromText(text, relPath, maxSymbols - imports.length));
    }
  }

  return {
    root: toPosix(root),
    package: packageInfo,
    entries,
    files: mapFiles,
    symbols,
    imports,
    importGroups: buildImportGroups(imports),
    summary: {
      filesScanned: mapFiles.length,
      symbolsIndexed: symbols.length,
      importsIndexed: imports.length,
      truncated: files.length >= maxFiles || symbols.length >= maxSymbols,
    },
  };
}

export const repoMapSchema = toOpenAITool({
  name: 'repo_map',
  description: 'Build a compact repository map with entry files, source files, and lightweight symbol index. Use before large code tasks to orient yourself before grep/read_file.',
  parameters: {
    type: 'object',
    properties: {
      path: { type: 'string', description: 'Repository root to scan. Defaults to current working directory.' },
      max_files: { type: 'number', default: 250, description: 'Maximum source files to scan.' },
      max_symbols: { type: 'number', default: 500, description: 'Maximum symbols to include.' },
      include_tests: { type: 'boolean', default: false, description: 'Whether to include test/spec files.' },
    },
  },
});

const repoMapHandler: ToolHandler = async (args, context) => {
  const root = typeof args.path === 'string' && args.path.trim() ? args.path.trim() : undefined;
  try {
    const result = await buildRepoMap({
      root,
      maxFiles: Number(args.max_files ?? args.maxFiles ?? 250),
      maxSymbols: Number(args.max_symbols ?? args.maxSymbols ?? 500),
      includeTests: Boolean(args.include_tests ?? args.includeTests ?? false),
    }, { signal: context.signal });
    return JSON.stringify(result);
  } catch (err) {
    return JSON.stringify({ error: `repo_map failed: ${err instanceof Error ? err.message : String(err)}` });
  }
};

export const repoMapTool: ToolEntry = {
  name: 'repo_map',
  toolset: 'file',
  schema: repoMapSchema,
  handler: repoMapHandler,
  isAsync: true,
  emoji: 'RM',
  maxResultSizeChars: 80_000,
};
