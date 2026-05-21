// ============================================================================
// Read file tool — read a file with line numbers, offset, and limit
// ============================================================================

import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const readFileSchema = toOpenAITool({
  name: 'read_file',
  description: 'Read a file from the filesystem',
  parameters: {
    type: 'object',
    properties: {
      path: {
        type: 'string',
        description: 'Path to the file to read',
      },
      offset: {
        type: 'number',
        default: 1,
        description: 'Line number to start reading from (1-indexed)',
      },
      limit: {
        type: 'number',
        default: 500,
        description: 'Maximum number of lines to read',
      },
    },
    required: ['path'],
  },
});

// ---- handler ----

const readFileHandler: ToolHandler = (args, _context) => {
  return new Promise<string>(async (resolve) => {
    const path = String(args.path ?? '');
    const offset = Math.max(1, Number(args.offset ?? 1));
    const limit = Math.max(1, Number(args.limit ?? 500));

    if (!path) {
      resolve(JSON.stringify({ error: 'No path provided' }));
      return;
    }

    try {
      if (!existsSync(path)) {
        resolve(JSON.stringify({ error: `File not found: ${path}` }));
        return;
      }

      const content = await readFile(path, 'utf-8');
      const lines = content.split('\n');

      const startIdx = offset - 1;
      if (startIdx >= lines.length) {
        resolve(
          JSON.stringify({
            content: '',
            totalLines: lines.length,
            message: `Offset ${offset} exceeds file length (${lines.length} lines)`,
          }),
        );
        return;
      }

      const sliced = lines.slice(startIdx, startIdx + limit);

      // cat -n format: right-aligned 6-digit line numbers
      const numbered = sliced
        .map((line, i) => {
          const lineNum = String(startIdx + i + 1).padStart(6, ' ');
          return `${lineNum}\t${line}`;
        })
        .join('\n');

      resolve(
        JSON.stringify({
          content: numbered,
          totalLines: lines.length,
          linesRead: sliced.length,
        }),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      resolve(JSON.stringify({ error: `Failed to read file: ${message}` }));
    }
  });
};

// ---- entry ----

export const readFileTool: ToolEntry = {
  name: 'read_file',
  toolset: 'file',
  schema: readFileSchema,
  handler: readFileHandler,
  isAsync: true,
  emoji: '📖',
  maxResultSizeChars: 100_000,
};
