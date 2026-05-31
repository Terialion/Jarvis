// ============================================================================
// Edit file tool — replace a string in a file
// ============================================================================

import { readFile, writeFile } from 'node:fs/promises';
import { statSync } from 'node:fs';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';
import { resolveSafePath, MAX_READ_SIZE } from './path-utils.js';

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

const editFileHandler: ToolHandler = async (args, _context) => {
  const filePath = String(args.path ?? '');
  const oldString = String(args.old_string ?? '');
  const newString = String(args.new_string ?? '');
  const replaceAll = Boolean(args.replace_all ?? false);
  const root = typeof args._workspaceRoot === 'string' ? args._workspaceRoot : undefined;

  const resolved = resolveSafePath(filePath, root);
  if (!resolved.ok) {
    return JSON.stringify({ error: resolved.error });
  }

  try {
    let stat;
    try {
      stat = statSync(resolved.path);
    } catch {
      return JSON.stringify({ error: `File not found: ${filePath}` });
    }
    if (stat.size > MAX_READ_SIZE) {
      return JSON.stringify({
        error: `File too large (${(stat.size / 1024 / 1024).toFixed(1)} MB). Max: ${MAX_READ_SIZE / 1024 / 1024} MB`,
      });
    }

    const content = await readFile(resolved.path, 'utf-8');

    if (!content.includes(oldString)) {
      return JSON.stringify({
        error: 'old_string not found in file',
        details: 'The exact text was not found in the file',
      });
    }

    if (replaceAll) {
      const count = content.split(oldString).length - 1;
      const updated = content.split(oldString).join(newString);
      await writeFile(resolved.path, updated, 'utf-8');
      return JSON.stringify({ ok: true, path: resolved.path, replacements: count });
    }

    // Require exact match to be unique
    const firstIdx = content.indexOf(oldString);
    const lastIdx = content.lastIndexOf(oldString);
    if (firstIdx !== lastIdx) {
      return JSON.stringify({
        error:
          'old_string is not unique in the file. Use replace_all=true to replace all occurrences, or provide a larger string with more surrounding context to make it unique.',
      });
    }

    const updated =
      content.slice(0, firstIdx) + newString + content.slice(firstIdx + oldString.length);
    await writeFile(resolved.path, updated, 'utf-8');
    // Compute line number and context lines for diff display
    const beforeEdit = content.slice(0, firstIdx);
    const lineNum = beforeEdit.split('\n').length;
    const allLines = content.split('\n');
    const oldLineCount = oldString.replace(/\n$/, '').split('\n').length;
    const contextBefore = allLines.slice(Math.max(0, lineNum - 3), lineNum - 1);
    const contextAfter = allLines.slice(lineNum - 1 + oldLineCount, lineNum - 1 + oldLineCount + 2);
    return JSON.stringify({
      ok: true,
      path: resolved.path,
      replacements: 1,
      line: lineNum,
      contextBefore,
      contextAfter,
      oldLineCount,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Failed to edit file: ${message}` });
  }
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
