// ============================================================================
// Read file tool — read text files with line numbers, images as base64, PDFs via pdf-parse
// ============================================================================

import { readFile } from 'node:fs/promises';
import { statSync } from 'node:fs';
import { extname } from 'node:path';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';
import { resolveSafePath, MAX_READ_SIZE } from './path-utils.js';

// ---- constants ----

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg']);

const IMAGE_MIME_TYPES: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.bmp': 'image/bmp',
  '.svg': 'image/svg+xml',
};

const MAX_PDF_PAGES = 20;

// ---- helpers ----

function isImage(filePath: string): boolean {
  const ext = extname(filePath).toLowerCase();
  return IMAGE_EXTENSIONS.has(ext);
}

function isPdf(filePath: string): boolean {
  return filePath.toLowerCase().endsWith('.pdf');
}

function parsePagesParam(pages: string | undefined): number[] | undefined {
  if (!pages || pages.trim() === '') return undefined;
  const trimmed = pages.trim();
  // "1-5" → [1,2,3,4,5]  |  "3" → [3]  |  "10-20" → [10,...,20]
  const match = trimmed.match(/^(\d+)(?:-(\d+))?$/);
  if (!match) return undefined;
  const start = parseInt(match[1], 10);
  const end = match[2] ? parseInt(match[2], 10) : start;
  if (start < 1 || end < start) return undefined;
  const count = end - start + 1;
  if (count > MAX_PDF_PAGES) return undefined;
  return Array.from({ length: count }, (_, i) => start + i);
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

// ---- schema ----

export const readFileSchema = toOpenAITool({
  name: 'read_file',
  description:
    'Read a file from the filesystem. Text files return line-numbered content. Image files (png, jpg, gif, webp, bmp, svg) return base64 data for multimodal processing. PDF files extract text via pdf-parse.',
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
        description: 'Line number to start reading from (1-indexed). For text and PDF files only.',
      },
      limit: {
        type: 'number',
        default: 500,
        description: 'Maximum number of lines to read. For text and PDF files only.',
      },
      pages: {
        type: 'string',
        description:
          'Optional for PDF files. Page range to read (e.g. "1-5", "3", "10-20"). Maximum 20 pages per request.',
      },
    },
    required: ['path'],
  },
});

// ---- handler ----

const readFileHandler: ToolHandler = async (args, _context) => {
  const filePath = String(args.path ?? '');
  const offset = Math.max(1, Number(args.offset ?? 1));
  const limit = Math.max(1, Number(args.limit ?? 500));
  const pages = typeof args.pages === 'string' ? args.pages : undefined;
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

    // ---- image files ----
    if (isImage(resolved.path)) {
      const ext = extname(resolved.path).toLowerCase();
      const mimeType = IMAGE_MIME_TYPES[ext] ?? 'application/octet-stream';

      if (stat.size > MAX_READ_SIZE) {
        return JSON.stringify({
          content: `[Image too large: ${filePath} (${formatFileSize(stat.size)})]`,
          type: 'image',
          mimeType,
          error: `File too large (${(stat.size / 1024 / 1024).toFixed(1)} MB). Max: ${MAX_READ_SIZE / 1024 / 1024} MB`,
        });
      }

      const buffer = await readFile(resolved.path);
      const base64 = buffer.toString('base64');

      return JSON.stringify({
        content: `[Image: ${filePath} (${mimeType}, ${formatFileSize(stat.size)})]`,
        type: 'image',
        mimeType,
        base64,
        size: stat.size,
      });
    }

    // ---- PDF files ----
    if (isPdf(resolved.path)) {
      if (stat.size > MAX_READ_SIZE) {
        return JSON.stringify({
          error: `File too large (${(stat.size / 1024 / 1024).toFixed(1)} MB). Max: ${MAX_READ_SIZE / 1024 / 1024} MB`,
        });
      }

      const pageNumbers = parsePagesParam(pages);

      // Lazy-load pdf-parse only when reading a PDF
      const { PDFParse } = await import('pdf-parse');
      const buffer = await readFile(resolved.path);
      const pdf = new PDFParse({ data: new Uint8Array(buffer) });

      const textResult = await pdf.getText(
        pageNumbers ? { partial: pageNumbers, pageJoiner: '' } : { pageJoiner: '' },
      );

      await pdf.destroy();

      const text = textResult.text ?? '';
      const lines = text.split('\n');
      const totalLines = lines.length;
      const totalPages = textResult.total;

      const startIdx = offset - 1;
      if (startIdx >= lines.length) {
        return JSON.stringify({
          content: '',
          totalLines: lines.length,
          totalPages,
          message: `Offset ${offset} exceeds extracted text length (${lines.length} lines)`,
        });
      }

      const sliced = lines.slice(startIdx, startIdx + limit);
      const numbered = sliced
        .map((line, i) => {
          const lineNum = String(startIdx + i + 1).padStart(6, ' ');
          return `${lineNum}\t${line}`;
        })
        .join('\n');

      return JSON.stringify({
        content: numbered,
        totalLines: lines.length,
        linesRead: sliced.length,
        totalPages,
        pagesRequested: pageNumbers ?? 'all',
      });
    }

    // ---- text files ----
    if (stat.size > MAX_READ_SIZE) {
      return JSON.stringify({
        error: `File too large (${(stat.size / 1024 / 1024).toFixed(1)} MB). Max: ${MAX_READ_SIZE / 1024 / 1024} MB`,
      });
    }

    const content = await readFile(resolved.path, 'utf-8');
    const lines = content.split('\n');

    const startIdx = offset - 1;
    if (startIdx >= lines.length) {
      return JSON.stringify({
        content: '',
        totalLines: lines.length,
        message: `Offset ${offset} exceeds file length (${lines.length} lines)`,
      });
    }

    const sliced = lines.slice(startIdx, startIdx + limit);

    // cat -n format: right-aligned 6-digit line numbers
    const numbered = sliced
      .map((line, i) => {
        const lineNum = String(startIdx + i + 1).padStart(6, ' ');
        return `${lineNum}\t${line}`;
      })
      .join('\n');

    return JSON.stringify({
      content: numbered,
      totalLines: lines.length,
      linesRead: sliced.length,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return JSON.stringify({ error: `Failed to read file: ${message}` });
  }
};

// ---- entry ----

export const readFileTool: ToolEntry = {
  name: 'read_file',
  toolset: 'file',
  schema: readFileSchema,
  handler: readFileHandler,
  isAsync: true,
  emoji: '📖',
  maxResultSizeChars: 5_000_000,
};
