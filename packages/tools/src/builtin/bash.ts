// ============================================================================
// Bash tool — execute shell commands via child_process
// ============================================================================

import * as fs from 'node:fs';
import { exec, type ChildProcess, type ExecOptions } from 'node:child_process';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';
import { getBackgroundTaskRegistry } from './task.js';

// ---- schema ----

export const bashSchema = toOpenAITool({
  name: 'bash',
  description: 'Execute a shell command',
  parameters: {
    type: 'object',
    properties: {
      command: {
        type: 'string',
        description: 'The command to execute',
      },
      workdir: {
        type: 'string',
        description: 'Working directory for the command',
      },
      timeout: {
        type: 'number',
        default: 120000,
        description: 'Maximum execution time in milliseconds',
      },
      run_in_background: {
        type: 'boolean',
        default: false,
        description: 'Set to true to run in the background. Returns a task_id for use with task_output/task_stop.',
      },
    },
    required: ['command'],
  },
});

// ---- shell detection ----

function detectShell(): string {
  if (process.platform !== 'win32') return '/bin/sh';

  // Prefer Git Bash when available — LLMs generate bash syntax
  const gitBashPaths = [
    'C:\\Program Files\\Git\\bin\\bash.exe',
    'C:\\Program Files (x86)\\Git\\bin\\bash.exe',
  ];
  for (const bashPath of gitBashPaths) {
    if (fs.existsSync(bashPath)) return bashPath;
  }

  // cmd.exe supports && chaining and some POSIX-like patterns
  return 'cmd.exe';
}

// ---- handler ----

function doExec(
  command: string,
  timeout: number,
  workdir?: string,
  signal?: AbortSignal,
): Promise<{ result?: string; error?: string }> {
  return new Promise((resolve) => {
    const options: ExecOptions = { timeout, maxBuffer: 10 * 1024 * 1024, cwd: workdir, shell: detectShell(), signal };
    let settled = false;
    let child: ChildProcess;
    const settle = (payload: { result?: string; error?: string }) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener('abort', onAbort);
      resolve(payload);
    };
    const onAbort = () => {
      if (child && !child.killed) {
        child.kill('SIGTERM');
        setTimeout(() => {
          if (!child.killed) child.kill('SIGKILL');
        }, 250);
      }
      settle({
        result: JSON.stringify({ exitCode: -1, stdout: '', stderr: '', killed: true, error: 'Tool interrupted' }),
      });
    };
    child = exec(command, options, (error, stdout, stderr) => {
      if (error) {
        settle({ result: JSON.stringify({ exitCode: (error as { code?: number }).code ?? 1, stdout: stdout || '', stderr: stderr || '', killed: (error as { killed?: boolean }).killed ?? false, error: error.message }) });
      } else {
        settle({ result: JSON.stringify({ exitCode: 0, stdout, stderr }) });
      }
    });
    if (signal?.aborted) {
      onAbort();
      return;
    }
    signal?.addEventListener('abort', onAbort, { once: true });
    const killTimer = setTimeout(() => { child.kill('SIGTERM'); setTimeout(() => { if (!child.killed) child.kill('SIGKILL'); }, 2000); }, timeout);
    child.on('close', () => clearTimeout(killTimer));
  });
}

const bashHandler: ToolHandler = (args, context) => {
  const command = String(args.command ?? '');
  const timeout = Number(args.timeout ?? 120_000);
  const workdir = args.workdir ? String(args.workdir) : undefined;
  const runInBackground = args.run_in_background === true;

  if (!command.trim()) return JSON.stringify({ error: 'No command provided' });

  if (runInBackground) {
    const registry = getBackgroundTaskRegistry();
    let cancelFn!: () => void;
    const taskPromise = new Promise<{ result?: string; error?: string }>((resolve) => {
      const options: ExecOptions = { timeout, maxBuffer: 10 * 1024 * 1024, cwd: workdir, shell: detectShell() };
      let settled = false;
      const child = exec(command, options, (error, stdout, stderr) => {
        if (settled) return;
        settled = true;
        if (error) {
          resolve({ result: JSON.stringify({ exitCode: (error as { code?: number }).code ?? 1, stdout: stdout || '', stderr: stderr || '', killed: (error as { killed?: boolean }).killed ?? false, error: error.message }) });
        } else {
          resolve({ result: JSON.stringify({ exitCode: 0, stdout, stderr }) });
        }
      });
      cancelFn = () => { if (!settled) { settled = true; child.kill('SIGKILL'); resolve({ result: JSON.stringify({ exitCode: -1, stdout: '', stderr: '', killed: true, error: 'Task cancelled' }) }); } };
      const killTimer = setTimeout(() => { child.kill('SIGTERM'); setTimeout(() => { if (!child.killed && !settled) child.kill('SIGKILL'); }, 2000); }, timeout);
      child.on('close', () => clearTimeout(killTimer));
    });
    const taskId = registry.register({ type: 'bash', status: 'running', description: `bash: ${command.slice(0, 80)}`, promise: taskPromise, cancel: cancelFn });
    return JSON.stringify({ task_id: taskId, status: 'running', message: `Background task "${taskId}" started: ${command.slice(0, 80)}` });
  }

  // Foreground mode
  return doExec(command, timeout, workdir, context.signal).then((r) => r.result ?? JSON.stringify({ error: 'Unknown error' }));
};

// ---- availability check ----

function bashCheckFn(): boolean {
  // On non-Windows, always available
  // On Windows, check for git-bash or WSL
  if (process.platform !== 'win32') return true;

  // Simple check: if we're on Windows, check common shell locations
  // For now, always return true on Windows too — PowerShell is always available
  return true;
}

// ---- entry ----

export const bashTool: ToolEntry = {
  name: 'bash',
  toolset: 'terminal',
  schema: bashSchema,
  handler: bashHandler,
  checkFn: bashCheckFn,
  isAsync: true,
  emoji: '💻',
  maxResultSizeChars: 50_000,
};
