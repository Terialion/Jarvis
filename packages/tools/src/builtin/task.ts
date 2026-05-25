// ============================================================================
// Task tools — create, update, and list structured task lists
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- in-memory task store ----

export interface TaskItem {
  id: string;
  subject: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed';
  createdAt: number;
}

const taskStore = new Map<string, TaskItem[]>();
let taskSeq = 0;

function getTasks(sessionId?: string): TaskItem[] {
  const key = sessionId ?? '_global';
  let tasks = taskStore.get(key);
  if (!tasks) {
    tasks = [];
    taskStore.set(key, tasks);
  }
  return tasks;
}

// ---- task_create ----

export const taskCreateSchema = toOpenAITool({
  name: 'task_create',
  description:
    'Create one or more structured tasks to track progress on complex multi-step work. Each task has a subject, description, and status. Use this to break down large requests into verifiable steps.',
  parameters: {
    type: 'object',
    properties: {
      tasks: {
        type: 'array',
        minItems: 1,
        description: 'List of tasks to create.',
        items: {
          type: 'object',
          properties: {
            subject: {
              type: 'string',
              description: 'Brief action-oriented title, e.g. "Fix login bug".',
            },
            description: {
              type: 'string',
              description: 'What needs to be done.',
            },
            status: {
              type: 'string',
              enum: ['pending', 'in_progress', 'completed'],
              description: 'Task status (default: pending).',
            },
          },
          required: ['subject', 'description'],
        },
      },
    },
    required: ['tasks'],
  },
});

const taskCreateHandler: ToolHandler = (args, context) => {
  const items = (args as { tasks?: Array<{ subject: string; description: string; status?: string }> }).tasks;
  if (!items || items.length === 0) {
    return JSON.stringify({ error: 'No tasks provided.' });
  }

  const tasks = getTasks(context.sessionId);
  const created: TaskItem[] = [];

  for (const item of items) {
    const task: TaskItem = {
      id: `task_${++taskSeq}`,
      subject: item.subject,
      description: item.description,
      status: (item.status as TaskItem['status']) ?? 'pending',
      createdAt: Date.now(),
    };
    tasks.push(task);
    created.push(task);
  }

  return JSON.stringify({
    message: `Created ${created.length} task(s).`,
    tasks: created.map((t) => ({ id: t.id, subject: t.subject, status: t.status })),
  });
};

// ---- task_update ----

export const taskUpdateSchema = toOpenAITool({
  name: 'task_update',
  description:
    'Update task status and details. Mark tasks as in_progress, completed, or pending. Only one task should be in_progress at a time.',
  parameters: {
    type: 'object',
    properties: {
      taskId: {
        type: 'string',
        description: 'Task ID to update (from task_list).',
      },
      status: {
        type: 'string',
        enum: ['pending', 'in_progress', 'completed', 'deleted'],
        description: 'New status.',
      },
      subject: {
        type: 'string',
        description: 'Updated task subject.',
      },
      description: {
        type: 'string',
        description: 'Updated task description.',
      },
    },
    required: ['taskId'],
  },
});

const taskUpdateHandler: ToolHandler = (args, context) => {
  const params = args as { taskId: string; status?: string; subject?: string; description?: string };
  const tasks = getTasks(context.sessionId);
  const task = tasks.find((t) => t.id === params.taskId);

  if (!task) {
    return JSON.stringify({ error: `Task not found: ${params.taskId}` });
  }

  if (params.status) {
    if (params.status === 'deleted') {
      const idx = tasks.indexOf(task);
      tasks.splice(idx, 1);
      return JSON.stringify({ message: `Deleted task: ${task.subject}`, taskId: task.id });
    }
    // Validate only one in_progress
    if (params.status === 'in_progress') {
      for (const t of tasks) {
        if (t.id !== task.id && t.status === 'in_progress') {
          return JSON.stringify({
            error: `Task "${t.subject}" is already in_progress. Complete it first.`,
          });
        }
      }
    }
    task.status = params.status as TaskItem['status'];
  }
  if (params.subject) task.subject = params.subject;
  if (params.description) task.description = params.description;

  return JSON.stringify({
    message: `Updated task: ${task.subject}`,
    task: { id: task.id, subject: task.subject, status: task.status },
  });
};

// ---- task_list ----

export const taskListSchema = toOpenAITool({
  name: 'task_list',
  description:
    'List all tasks for the current session with their status. Use this to review progress before taking the next step.',
  parameters: {
    type: 'object',
    properties: {
      status: {
        type: 'string',
        enum: ['pending', 'in_progress', 'completed'],
        description: 'Filter by status (optional).',
      },
    },
  },
});

const taskListHandler: ToolHandler = (args, context) => {
  const params = args as { status?: string };
  const tasks = getTasks(context.sessionId);

  let filtered = tasks;
  if (params.status) {
    filtered = tasks.filter((t) => t.status === params.status);
  }

  if (filtered.length === 0) {
    return JSON.stringify({
      message: tasks.length > 0 ? 'No tasks match the filter.' : 'No tasks yet. Create tasks with task_create.',
      tasks: [],
      counts: { pending: 0, in_progress: 0, completed: 0 },
    });
  }

  const counts = {
    pending: tasks.filter((t) => t.status === 'pending').length,
    in_progress: tasks.filter((t) => t.status === 'in_progress').length,
    completed: tasks.filter((t) => t.status === 'completed').length,
  };

  return JSON.stringify({
    tasks: filtered.map((t) => ({
      id: t.id,
      subject: t.subject,
      status: t.status,
    })),
    counts,
  });
};

// ---- task_get ----

export const taskGetSchema = toOpenAITool({
  name: 'task_get',
  description:
    'Retrieve a single task by ID. Returns full task details including subject, description, and status.',
  parameters: {
    type: 'object',
    properties: {
      taskId: {
        type: 'string',
        description: 'Task ID to retrieve (from task_list).',
      },
    },
    required: ['taskId'],
  },
});

const taskGetHandler: ToolHandler = (args, context) => {
  const taskId = String(args.taskId ?? '');
  const tasks = getTasks(context.sessionId);
  const task = tasks.find((t) => t.id === taskId);

  if (!task) {
    return JSON.stringify({ error: `Task not found: ${taskId}` });
  }

  return JSON.stringify({
    id: task.id,
    subject: task.subject,
    description: task.description,
    status: task.status,
    createdAt: task.createdAt,
  });
};

// ---- entries ----

export const taskCreateTool: ToolEntry = {
  name: 'task_create',
  toolset: 'orchestration',
  schema: taskCreateSchema,
  handler: taskCreateHandler,
  emoji: '📋',
  description: 'Create structured tasks for tracking complex work.',
};

export const taskUpdateTool: ToolEntry = {
  name: 'task_update',
  toolset: 'orchestration',
  schema: taskUpdateSchema,
  handler: taskUpdateHandler,
  emoji: '✅',
  description: 'Update task status and details.',
};

export const taskListTool: ToolEntry = {
  name: 'task_list',
  toolset: 'orchestration',
  schema: taskListSchema,
  handler: taskListHandler,
  emoji: '📊',
  description: 'List tasks with status for the current session.',
};

export const taskGetTool: ToolEntry = {
  name: 'task_get',
  toolset: 'orchestration',
  schema: taskGetSchema,
  handler: taskGetHandler,
  emoji: '🔍',
  description: 'Get full details of a single task by ID.',
};

// ============================================================================
// Background task registry
// ============================================================================

export interface BackgroundTask {
  id: string;
  type: 'bash' | 'agent';
  status: 'running' | 'completed' | 'errored';
  description: string;
  startedAt: number;
  promise: Promise<{ result?: string; error?: string }>;
  cancel: () => void;
}

const backgroundTasks = new Map<string, BackgroundTask>();
let bgTaskSeq = 0;

export function getBackgroundTaskRegistry() {
  return {
    register(task: Omit<BackgroundTask, 'id' | 'startedAt'>): string {
      const id = `bg_${++bgTaskSeq}`;
      const bgTask: BackgroundTask = { ...task, id, startedAt: Date.now() };
      backgroundTasks.set(id, bgTask);
      bgTask.promise
        .then(() => { const t = backgroundTasks.get(id); if (t) t.status = 'completed'; })
        .catch(() => { const t = backgroundTasks.get(id); if (t) t.status = 'errored'; })
        .finally(() => { setTimeout(() => backgroundTasks.delete(id), 10 * 60_000); });
      return id;
    },
    get(id: string): BackgroundTask | undefined { return backgroundTasks.get(id); },
    list(): BackgroundTask[] { return [...backgroundTasks.values()]; },
    cancel(id: string): boolean {
      const task = backgroundTasks.get(id);
      if (!task) return false;
      if (task.status === 'running') task.cancel();
      backgroundTasks.delete(id);
      return true;
    },
  };
}

// ---- task_output ----

export const taskOutputSchema = toOpenAITool({
  name: 'task_output',
  description: 'Retrieve output from a running or completed background task (shell, agent, or remote session). Takes a task_id and optionally block=true to wait for completion.',
  parameters: {
    type: 'object',
    properties: {
      task_id: { type: 'string', description: 'The task ID to get output from.' },
      block: { type: 'boolean', default: true, description: 'Whether to wait for completion.' },
      timeout: { type: 'number', default: 30000, description: 'Max wait time in ms.' },
    },
    required: ['task_id'],
  },
});

const taskOutputHandler: ToolHandler = async (args, _context) => {
  const taskId = String(args.task_id ?? '').trim();
  const block = args.block !== false && args.block !== 'false';
  const timeout = Math.min(600_000, Math.max(1000, Number(args.timeout ?? 30000)));
  if (!taskId) return JSON.stringify({ error: 'Missing required parameter: task_id' });
  const registry = getBackgroundTaskRegistry();
  const task = registry.get(taskId);
  if (!task) return JSON.stringify({ error: `Background task not found: ${taskId}` });
  if (!block) return JSON.stringify({ task_id: task.id, type: task.type, status: task.status, description: task.description, message: 'Task status checked without blocking.' });
  try {
    const result = await Promise.race([
      task.promise,
      new Promise<{ _timeout: true }>((r) => setTimeout(() => r({ _timeout: true }), timeout)),
    ]);
    if ((result as { _timeout?: boolean })._timeout) return JSON.stringify({ task_id: task.id, type: task.type, status: task.status, message: `Task still running after ${timeout}ms timeout.` });
    const { result: output, error } = result as { result?: string; error?: string };
    return JSON.stringify({ task_id: task.id, type: task.type, status: error ? 'errored' : 'completed', output: output ?? '', error: error ?? null });
  } catch (err) {
    return JSON.stringify({ task_id: task.id, status: 'errored', error: err instanceof Error ? err.message : String(err) });
  }
};

// ---- task_stop ----

export const taskStopSchema = toOpenAITool({
  name: 'task_stop',
  description: 'Stop a running background task by its ID.',
  parameters: {
    type: 'object',
    properties: { task_id: { type: 'string', description: 'The ID of the background task to stop.' } },
    required: ['task_id'],
  },
});

const taskStopHandler: ToolHandler = (args, _context) => {
  const taskId = String(args.task_id ?? '').trim();
  if (!taskId) return JSON.stringify({ error: 'Missing required parameter: task_id' });
  const registry = getBackgroundTaskRegistry();
  const ok = registry.cancel(taskId);
  return JSON.stringify(ok ? { message: `Background task "${taskId}" stopped.` } : { error: `Background task not found: ${taskId}` });
};

export const taskOutputTool: ToolEntry = {
  name: 'task_output', toolset: 'orchestration', schema: taskOutputSchema, handler: taskOutputHandler, isAsync: true, emoji: '📤', description: 'Retrieve output from a background task.',
};

export const taskStopTool: ToolEntry = {
  name: 'task_stop', toolset: 'orchestration', schema: taskStopSchema, handler: taskStopHandler, isAsync: false, emoji: '🛑', description: 'Stop a running background task.',
};
