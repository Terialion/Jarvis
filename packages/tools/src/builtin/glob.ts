// ============================================================================
// Glob tool — file pattern matching (no npm dependency)
// ============================================================================

import { readdir, stat } from 'node:fs/promises';
import { join, resolve, relative, sep } from 'node:path';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const globSchema = toOpenAITool({
  name: 'glob',
  description: 'Find files matching a glob pattern',
  parameters: {
    type: 'object',
    properties: {
      pattern: {
        type: 'string',
        description: 'Glob pattern (supports **, *, ?)',
      },
      path: {
        type: 'string',
        description: 'Directory to search (default: current working directory)',
      },
    },
    required: ['pattern'],
  },
});

// ---- glob engine ----

interface GlobSegment {
  /** True if this segment is '**' (recursive wildcard) */
  recursive: boolean;
  /** The literal parts and wildcards to match */
  pattern: string;
}

/**
 * Parse a glob pattern into segments separated by '/' (or '\').
 * Example: "src/** /*.ts" -> [{recursive: false, pattern: "src"}, {recursive: true}, {recursive: false, pattern: "*.ts"}]
 */
function parseSegments(pattern: string): GlobSegment[] {
  const rawSegments = pattern.split(/[/\\]/);
  const segments: GlobSegment[] = [];
  for (const seg of rawSegments) {
    if (seg === '**') {
      segments.push({ recursive: true, pattern: '**' });
    } else if (seg === '') {
      // skip empty segments from leading/trailing/double slashes
      continue;
    } else {
      segments.push({ recursive: false, pattern: seg });
    }
  }
  return segments;
}

/**
 * Convert a glob pattern segment to a RegExp.
 * * matches any characters except path separator
 * ? matches a single character except path separator
 * Escaped characters: . + ^ $ { } [ ] ( ) | \
 */
function segmentToRegex(pattern: string): RegExp {
  let regexStr = '^';
  for (const ch of pattern) {
    if (ch === '*') {
      regexStr += `[^${escapeRe(sep)}]*`;
    } else if (ch === '?') {
      regexStr += `[^${escapeRe(sep)}]`;
    } else if ('.+^${}[]()|\\'.includes(ch)) {
      regexStr += '\\' + ch;
    } else {
      regexStr += ch;
    }
  }
  regexStr += '$';
  return new RegExp(regexStr);
}

function escapeRe(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Match a filename against a non-recursive glob segment.
 */
function matchSegment(filename: string, pattern: string): boolean {
  if (pattern === '' || pattern === '*') return true;
  return segmentToRegex(pattern).test(filename);
}

// ---- walk implementation ----

interface WalkOptions {
  cwd: string;
  segments: GlobSegment[];
  maxResults?: number;
  signal?: AbortSignal;
}

async function walkGlob(options: WalkOptions): Promise<string[]> {
  const { cwd, segments, maxResults = 10_000, signal } = options;
  const results: string[] = [];

  async function walk(dir: string, segIdx: number): Promise<void> {
    if (signal?.aborted) {
      throw new Error('Tool interrupted');
    }
    if (results.length >= maxResults) return;

    // If we've matched all segments, the current file/dir matches
    if (segIdx >= segments.length) {
      results.push(relative(cwd, dir).replace(/\\/g, '/'));
      return;
    }

    const segment = segments[segIdx];

    if (segment.recursive) {
      // '**' — match zero or more directories
      // Option A: skip this segment (match zero directories)
      await walk(dir, segIdx + 1);
      if (results.length >= maxResults) return;

      // Option B: descend into subdirectories and try to match later
      try {
        const entries = await readdir(dir, { withFileTypes: true });
        for (const entry of entries) {
          if (results.length >= maxResults) return;
          if (entry.isDirectory()) {
            const fullPath = join(dir, entry.name);
            await walk(fullPath, segIdx); // stay on '**' for deeper recursion
            if (results.length >= maxResults) return;
          }
        }
      } catch {
        // Skip unreadable directories
      }
    } else {
      // Regular segment — match filenames at the current level
      // On the last segment, also match files; otherwise only match directories
      const isLastSeg = segIdx === segments.length - 1;
      try {
        const entries = await readdir(dir, { withFileTypes: true });
        for (const entry of entries) {
          if (results.length >= maxResults) return;

          if (!matchSegment(entry.name, segment.pattern)) continue;

          if (isLastSeg) {
            // Last segment — match both files and dirs
            results.push(
              relative(cwd, join(dir, entry.name)).replace(/\\/g, '/'),
            );
          } else if (entry.isDirectory()) {
            // Intermediate segment — only descend into dirs
            await walk(join(dir, entry.name), segIdx + 1);
          }
        }
      } catch {
        // Skip unreadable directories
      }
    }
  }

  await walk(cwd, 0);
  return results.slice(0, maxResults);
}

// ---- handler ----

const globHandler: ToolHandler = async (args, _context) => {
  const pattern = String(args.pattern ?? '');
  const rawPath: string = args.path ? String(args.path) : process.cwd();
  const basePath = resolve(rawPath);

  if (!pattern) {
    return JSON.stringify({ error: 'No pattern provided' });
  }

  try {
    const segments = parseSegments(pattern);
    if (segments.length === 0) {
      return JSON.stringify({ matches: [] });
    }

    const matches = await walkGlob({ cwd: basePath, segments, signal: _context.signal });
    return JSON.stringify({ matches });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Glob failed: ${message}` });
  }
};

// ---- entry ----

export const globTool: ToolEntry = {
  name: 'glob',
  toolset: 'file',
  schema: globSchema,
  handler: globHandler,
  isAsync: true,
  emoji: '🔍',
  maxResultSizeChars: 50_000,
};
