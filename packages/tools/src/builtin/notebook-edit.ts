// ============================================================================
// Notebook edit tool — replace, insert, or delete cells in Jupyter notebooks
// ============================================================================

import { readFileSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';
import { resolveSafePath } from './path-utils.js';

// ---- notebook types ----

interface NotebookCell {
  cell_type: 'code' | 'markdown' | 'raw';
  source: string[];
  metadata?: Record<string, unknown>;
  outputs?: unknown[];
  execution_count?: number | null;
  id?: string;
}

interface Notebook {
  cells: NotebookCell[];
  metadata: Record<string, unknown>;
  nbformat: number;
  nbformat_minor: number;
}

// ---- schema ----

export const notebookEditSchema = toOpenAITool({
  name: 'notebook_edit',
  description:
    'Completely replaces the contents of a specific cell in a Jupyter notebook (.ipynb file) with new source. Use edit_mode=insert to add a new cell at the index specified by cell_number. Use edit_mode=delete to delete the cell at the index specified by cell_number.',
  parameters: {
    type: 'object',
    properties: {
      notebook_path: {
        type: 'string',
        description: 'The absolute path to the Jupyter notebook file to edit.',
      },
      cell_number: {
        type: 'number',
        description:
          'The 0-indexed cell number to replace or delete. For insert, the new cell is inserted after this index (omit to insert at the beginning).',
      },
      new_source: {
        type: 'string',
        description: 'The new source for the cell.',
      },
      cell_type: {
        type: 'string',
        enum: ['code', 'markdown'],
        description: 'The type of the cell. Required for insert and replace.',
      },
      edit_mode: {
        type: 'string',
        enum: ['replace', 'insert', 'delete'],
        description: 'The type of edit: replace (default), insert, or delete.',
      },
    },
    required: ['notebook_path', 'new_source'],
  },
});

// ---- helpers ----

function generateCellId(): string {
  return `cell_${crypto.randomUUID().slice(0, 8)}`;
}

function readNotebook(path: string): Notebook {
  const content = readFileSync(path, 'utf-8');
  return JSON.parse(content) as Notebook;
}

function validateNotebook(nb: unknown): nb is Notebook {
  if (!nb || typeof nb !== 'object') return false;
  const n = nb as Record<string, unknown>;
  if (!Array.isArray(n.cells)) return false;
  if (typeof n.nbformat !== 'number') return false;
  return true;
}

// ---- handler ----

const notebookEditHandler: ToolHandler = async (args, _context) => {
  const notebookPath = String(args.notebook_path ?? '');
  const newSource = String(args.new_source ?? '');
  const editMode = (String(args.edit_mode ?? 'replace')) as 'replace' | 'insert' | 'delete';
  const cellType = (String(args.cell_type ?? 'code')) as 'code' | 'markdown';
  const cellNumber = args.cell_number !== undefined ? Number(args.cell_number) : undefined;
  const root = typeof args._workspaceRoot === 'string' ? args._workspaceRoot : undefined;

  const resolved = resolveSafePath(notebookPath, root);
  if (!resolved.ok) {
    return JSON.stringify({ error: resolved.error });
  }

  // Validate .ipynb extension
  if (!resolved.path.endsWith('.ipynb')) {
    return JSON.stringify({ error: 'File must be a Jupyter notebook (.ipynb)' });
  }

  let nb: Notebook;
  try {
    nb = readNotebook(resolved.path);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Failed to read notebook: ${message}` });
  }

  if (!validateNotebook(nb)) {
    return JSON.stringify({ error: 'Invalid notebook format' });
  }

  try {
    switch (editMode) {
      case 'replace': {
        if (cellNumber === undefined) {
          return JSON.stringify({ error: 'cell_number is required for replace mode' });
        }
        if (cellNumber < 0 || cellNumber >= nb.cells.length) {
          return JSON.stringify({
            error: `Cell index ${cellNumber} out of range (0-${nb.cells.length - 1})`,
          });
        }

        const oldSource = nb.cells[cellNumber].source.join('');
        nb.cells[cellNumber] = {
          cell_type: cellType,
          source: newSource.split('\n').map((line, i, arr) =>
            i < arr.length - 1 ? line + '\n' : line,
          ),
          metadata: nb.cells[cellNumber].metadata ?? {},
          outputs: cellType === 'code' ? [] : undefined,
          execution_count: cellType === 'code' ? null : undefined,
          id: nb.cells[cellNumber].id ?? generateCellId(),
        };

        await writeFile(resolved.path, JSON.stringify(nb, null, 1) + '\n', 'utf-8');
        return JSON.stringify({
          ok: true,
          path: resolved.path,
          edit_mode: 'replace',
          cell_number: cellNumber,
          old_source_length: oldSource.length,
          new_source_length: newSource.length,
        });
      }

      case 'insert': {
        const insertAt = cellNumber !== undefined ? cellNumber + 1 : 0;
        if (insertAt < 0 || insertAt > nb.cells.length) {
          return JSON.stringify({
            error: `Insert position ${insertAt} out of range (0-${nb.cells.length})`,
          });
        }

        const newCell: NotebookCell = {
          cell_type: cellType,
          source: newSource.split('\n').map((line, i, arr) =>
            i < arr.length - 1 ? line + '\n' : line,
          ),
          metadata: {},
          outputs: cellType === 'code' ? [] : undefined,
          execution_count: cellType === 'code' ? null : undefined,
          id: generateCellId(),
        };

        nb.cells.splice(insertAt, 0, newCell);

        await writeFile(resolved.path, JSON.stringify(nb, null, 1) + '\n', 'utf-8');
        return JSON.stringify({
          ok: true,
          path: resolved.path,
          edit_mode: 'insert',
          cell_number: insertAt,
          new_source_length: newSource.length,
        });
      }

      case 'delete': {
        if (cellNumber === undefined) {
          return JSON.stringify({ error: 'cell_number is required for delete mode' });
        }
        if (cellNumber < 0 || cellNumber >= nb.cells.length) {
          return JSON.stringify({
            error: `Cell index ${cellNumber} out of range (0-${nb.cells.length - 1})`,
          });
        }

        const removed = nb.cells[cellNumber];
        nb.cells.splice(cellNumber, 1);

        await writeFile(resolved.path, JSON.stringify(nb, null, 1) + '\n', 'utf-8');
        return JSON.stringify({
          ok: true,
          path: resolved.path,
          edit_mode: 'delete',
          cell_number: cellNumber,
          removed_cell_type: removed.cell_type,
          removed_source_preview: removed.source.join('').slice(0, 200),
        });
      }

      default:
        return JSON.stringify({ error: `Unknown edit_mode: ${editMode}` });
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Failed to edit notebook: ${message}` });
  }
};

// ---- entry ----

export const notebookEditTool: ToolEntry = {
  name: 'notebook_edit',
  toolset: 'file',
  schema: notebookEditSchema,
  handler: notebookEditHandler,
  isAsync: true,
  emoji: '📓',
  description: 'Edit Jupyter notebook cells (replace, insert, delete).',
};