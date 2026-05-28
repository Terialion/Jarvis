// ============================================================================
// Write file tool — create or overwrite a file
// ============================================================================

import { stat, writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';
import { resolveSafePath } from './path-utils.js';

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

const writeFileHandler: ToolHandler = async (args, _context) => {
  const filePath = String(args.path ?? '');
  const content = String(args.content ?? '');
  const root = typeof args._workspaceRoot === 'string' ? args._workspaceRoot : undefined;

  const resolved = resolveSafePath(filePath, root);
  if (!resolved.ok) {
    return JSON.stringify({ error: resolved.error });
  }

  try {
    let existedBefore = false;
    try {
      await stat(resolved.path);
      existedBefore = true;
    } catch {
      existedBefore = false;
    }

    await mkdir(dirname(resolved.path), { recursive: true });
    await writeFile(resolved.path, content, 'utf-8');

    return JSON.stringify({
      ok: true,
      path: resolved.path,
      existedBefore,
      bytesWritten: Buffer.byteLength(content, 'utf-8'),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Failed to write file: ${message}` });
  }
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
