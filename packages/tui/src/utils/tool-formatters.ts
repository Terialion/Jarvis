import type { MessageContent } from '../vendor/ui/MessageList.js';

export const TASK_TOOLS = new Set(['task_create', 'task_update', 'task_list']);
export const FILE_MODIFYING_TOOLS = new Set(['write', 'edit', 'bash']);

export function parseToolContent(name: string, raw: string): MessageContent | null {
  if (!TASK_TOOLS.has(name)) return null;
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    const tasks = (Array.isArray(data.tasks) ? data.tasks : data.task ? [data.task] : []) as Array<{
      id: string; subject: string; status: string;
    }>;
    const counts = (data.counts ?? { pending: 0, in_progress: 0, completed: 0 }) as {
      pending: number; in_progress: number; completed: number;
    };
    return {
      type: 'task_result',
      tasks: tasks.map((t) => ({ id: t.id, subject: t.subject, status: t.status as 'pending' | 'in_progress' | 'completed' })),
      counts,
    };
  } catch { return null; }
}

export function extractModifiedFiles(toolName: string, toolResult: string): string[] {
  const files: string[] = [];
  if (toolName === 'write' || toolName === 'edit') {
    const match = toolResult.match(/^\[(?:wrote|edited)\]\s+(.+)$/m);
    if (match) files.push(match[1].trim());
  }
  return files;
}

export function safeJsonParse(raw: string): Record<string, unknown> | null {
  try { return JSON.parse(raw); } catch { return null; }
}

export interface FileChange {
  filename: string;
  added: number;
  removed: number;
}

export function computeFileChange(toolName: string, toolResult: string): FileChange | null {
  if (toolName !== 'write' && toolName !== 'edit') return null;
  const parsed = safeJsonParse(toolResult);
  if (!parsed) return null;
  const filename = (parsed['path'] || parsed['file'] || parsed['filename'] || '') as string;
  if (!filename) return null;
  if (toolName === 'write') {
    const content = (parsed['content'] || '') as string;
    return { filename, added: content.split('\n').length, removed: 0 };
  }
  const oldStr = (parsed['old_string'] || '') as string;
  const newStr = (parsed['new_string'] || '') as string;
  return {
    filename,
    added: newStr ? newStr.split('\n').length : 0,
    removed: oldStr ? oldStr.split('\n').length : 0,
  };
}

export function formatFileChangeSummary(changes: FileChange[]): string {
  return changes.map((c) => {
    const display = c.filename.replace(/\\/g, '/');
    const parts: string[] = [];
    if (c.added > 0) parts.push(`Added ${c.added}`);
    if (c.removed > 0) parts.push(`Removed ${c.removed}`);
    const summary = parts.length > 0 ? parts.join(', ') : 'modified';
    return `● ${display}\n  ⎿  ${summary} lines`;
  }).join('\n');
}
