// ============================================================================
// Edit file tool — replace a string in a file
// ============================================================================

import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const editFileSchema = toOpenAITool({
  name: 'edit_file',
  description: 'Replace a string in a file',
  parameters: {
    type: 'object',
    properties: {
      path: {
        type: 'string',
        description: 'Path to the file to edit',
      },
      old_string: {
        type: 'string',
        description: 'The exact string to replace',
      },
      new_string: {
        type: 'string',
        description: 'The replacement string',
      },
      replace_all: {
        type: 'boolean',
        default: false,
        description: 'If true, replace all occurrences; otherwise require exactly one match',
      },
    },
    required: ['path', 'old_string', 'new_string'],
  },
});

// ---- handler ----

const editFileHandler: ToolHandler = (args, _context) => {
  return new Promise<string>(async (resolve) => {
    const path = String(args.path ?? '');
    const oldString = String(args.old_string ?? '');
    const newString = String(args.new_string ?? '');
    const replaceAll = Boolean(args.replace_all ?? false);

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

      if (!content.includes(oldString)) {
        resolve(
          JSON.stringify({
            error: `old_string not found in file`,
            details: 'The exact text was not found in the file',
          }),
        );
        return;
      }

      if (replaceAll) {
        const count = content.split(oldString).length - 1;
        const updated = content.split(oldString).join(newString);
        await writeFile(path, updated, 'utf-8');
        resolve(
          JSON.stringify({
            ok: true,
            path,
            replacements: count,
          }),
        );
      } else {
        // Require exact match to be unique
        const firstIdx = content.indexOf(oldString);
        const lastIdx = content.lastIndexOf(oldString);
        if (firstIdx !== lastIdx) {
          resolve(
            JSON.stringify({
              error:
                'old_string is not unique in the file. Use replace_all=true to replace all occurrences, or provide a larger string with more surrounding context to make it unique.',
            }),
          );
          return;
        }

        const updated =
          content.slice(0, firstIdx) + newString + content.slice(firstIdx + oldString.length);
        await writeFile(path, updated, 'utf-8');
        resolve(
          JSON.stringify({
            ok: true,
            path,
            replacements: 1,
          }),
        );
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      resolve(JSON.stringify({ error: `Failed to edit file: ${message}` }));
    }
  });
};

// ---- entry ----

export const editFileTool: ToolEntry = {
  name: 'edit_file',
  toolset: 'file',
  schema: editFileSchema,
  handler: editFileHandler,
  isAsync: true,
  emoji: '📝',
};
