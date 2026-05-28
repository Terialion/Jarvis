// ============================================================================
// Grep tool — search file contents with regex
// ============================================================================

import { readFile, readdir } from 'node:fs/promises';
import { existsSync, statSync } from 'node:fs';
import { join, resolve, relative } from 'node:path';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';
import { matchGlob } from './glob-utils.js';

// ---- schema ----

export type GrepOutputMode = 'content' | 'files_with_matches' | 'count';

export const grepSchema = toOpenAITool({
  name: 'grep',
  description: 'Search file contents with regex',
  parameters: {
    type: 'object',
    properties: {
      pattern: {
        type: 'string',
        description: 'Regular expression to search for',
      },
      path: {
        type: 'string',
        description: 'File or directory to search in (default: cwd)',
      },
      glob: {
        type: 'string',
        description: 'Glob pattern to filter files (e.g. "*.ts")',
      },
      output_mode: {
        type: 'string',
        enum: ['content', 'files_with_matches', 'count'],
        description: 'Output mode: "content" shows matching lines, "files_with_matches" lists files, "count" shows match counts',
      },
    },
    required: ['pattern'],
  },
});

// ---- handler ----

interface GrepArgs {
  pattern: string;
  path?: string;
  glob?: string;
  output_mode?: GrepOutputMode;
  head_limit?: number;
  offset?: number;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

async function walkFiles(
  dir: string,
  globPattern: string | undefined,
  results: string[],
  maxResults: number = 10_000,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    throw new Error('Tool interrupted');
  }
  try {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (signal?.aborted) {
        throw new Error('Tool interrupted');
      }
      if (results.length >= maxResults) return;
      const fullPath = join(dir, entry.name);
      if (entry.isDirectory()) {
        // Skip common non-source directories
        const skipDirs = new Set([
          'node_modules', '.git', '.svn', '.hg', '__pycache__', 'dist', 'build', '.next', '.turbo',
        ]);
        if (skipDirs.has(entry.name)) continue;
        if (entry.name.startsWith('.')) continue;
        await walkFiles(fullPath, globPattern, results, maxResults, signal);
      } else if (entry.isFile()) {
        if (globPattern) {
          const relPath = relative(dir, fullPath).replace(/\\/g, '/');
          if (matchGlob(relPath, globPattern)) {
            results.push(fullPath);
          }
        } else {
          results.push(fullPath);
        }
      }
    }
  } catch {
    // Skip unreadable directories
  }
}

const grepHandler: ToolHandler = async (args, _context) => {
  const pattern = String(args.pattern ?? '');
  const rawPath: string = args.path ? String(args.path) : process.cwd();
  const basePath = resolve(rawPath);
  const globFilter = args.glob ? String(args.glob) : undefined;
  const outputMode: GrepOutputMode = (args.output_mode as GrepOutputMode) ?? 'content';
  const headLimit = Number(args.head_limit ?? 250);
  const headOffset = Number(args.offset ?? 0);

  if (!pattern) {
    return JSON.stringify({ error: 'No pattern provided' });
  }

  let regex: RegExp;
  try {
    regex = new RegExp(pattern, 'gm');
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Invalid regex: ${message}` });
  }

  // Determine files to search
  let filesToSearch: string[] = [];

  try {
    const st = statSync(basePath);
    if (st.isFile()) {
      filesToSearch = [basePath];
    } else if (st.isDirectory()) {
        await walkFiles(basePath, globFilter, filesToSearch, 10_000, _context.signal);
    } else {
      return JSON.stringify({ error: `Path does not exist: ${basePath}` });
    }
  } catch {
    return JSON.stringify({ error: `Cannot access path: ${basePath}` });
  }

  // Search files
  const fileResults: Map<string, { lines: string[]; count: number }> = new Map();

  for (const filePath of filesToSearch) {
    if (_context.signal?.aborted) {
      throw new Error('Tool interrupted');
    }
    try {
      const size = statSync(filePath).size;
      if (size > MAX_FILE_SIZE) continue;

      const content = await readFile(filePath, 'utf-8');
      const lines = content.split('\n');
      const matches: string[] = [];
      let matchCount = 0;

      regex.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = regex.exec(content)) !== null) {
        matchCount++;
        const lineNum = content.slice(0, match.index).split('\n').length;
        const line = lines[lineNum - 1] ?? '';
        const relPath = relative(basePath, filePath).replace(/\\/g, '/');
        matches.push(`${relPath}:${lineNum}:${line}`);
      }

      if (matchCount > 0) {
        fileResults.set(filePath, { lines: matches, count: matchCount });
      }
    } catch {
      // Skip unreadable files
    }
  }

  // Format output
  switch (outputMode) {
    case 'files_with_matches': {
      const fileList = Array.from(fileResults.keys())
        .map((f) => relative(basePath, f).replace(/\\/g, '/'))
        .slice(headOffset, headOffset + headLimit);
      return JSON.stringify({ files: fileList });
    }
    case 'count': {
      const entries = Array.from(fileResults.entries()).map(([f, r]) => ({
        file: relative(basePath, f).replace(/\\/g, '/'),
        count: r.count,
      }));
      const sliced = entries.slice(headOffset, headOffset + (headLimit || 250));
      return JSON.stringify({ counts: sliced });
    }
    case 'content':
    default: {
      let allLines: string[] = [];
      for (const [, result] of fileResults) {
        allLines = allLines.concat(result.lines);
      }
      const sliced = allLines.slice(headOffset, headOffset + (headLimit || 250));
      return JSON.stringify({ matches: sliced });
    }
  }
};

// ---- entry ----

export const grepTool: ToolEntry = {
  name: 'grep',
  toolset: 'file',
  schema: grepSchema,
  handler: grepHandler,
  isAsync: true,
  emoji: '🔎',
  maxResultSizeChars: 50_000,
};
