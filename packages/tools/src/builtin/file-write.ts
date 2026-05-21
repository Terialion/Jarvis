// ============================================================================
// Write file tool — create or overwrite a file
// ============================================================================

import { writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const writeFileSchema = toOpenAITool({
  name: 'write_file',
  description: 'Create or overwrite a file',
  parameters: {
    type: 'object',
    properties: {
      path: {
        type: 'string',
        description: 'Path to the file to write',
      },
      content: {
        type: 'string',
        description: 'Content to write to the file',
      },
    },
    required: ['path', 'content'],
  },
});

// ---- handler ----

const writeFileHandler: ToolHandler = (args, _context) => {
  return new Promise<string>(async (resolve) => {
    const path = String(args.path ?? '');
    const content = String(args.content ?? '');

    if (!path) {
      resolve(JSON.stringify({ error: 'No path provided' }));
      return;
    }

    try {
      // Create parent directories recursively
      const dir = dirname(path);
      await mkdir(dir, { recursive: true });

      await writeFile(path, content, 'utf-8');

      resolve(
        JSON.stringify({
          ok: true,
          path,
          bytesWritten: Buffer.byteLength(content, 'utf-8'),
        }),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      resolve(JSON.stringify({ error: `Failed to write file: ${message}` }));
    }
  });
};

// ---- entry ----

export const writeFileTool: ToolEntry = {
  name: 'write_file',
  toolset: 'file',
  schema: writeFileSchema,
  handler: writeFileHandler,
  isAsync: true,
  emoji: '✏️',
};
