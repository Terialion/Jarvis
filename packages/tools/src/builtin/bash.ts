// ============================================================================
// Bash tool — execute shell commands via child_process
// ============================================================================

import * as fs from 'node:fs';
import { exec, type ExecOptions } from 'node:child_process';
import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';

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

const bashHandler: ToolHandler = (args, _context) => {
  return new Promise<string>((resolve) => {
    const command = String(args.command ?? '');
    const timeout = Number(args.timeout ?? 120_000);
    const workdir = args.workdir ? String(args.workdir) : undefined;

    if (!command.trim()) {
      resolve(JSON.stringify({ error: 'No command provided' }));
      return;
    }

    const options: ExecOptions = {
      timeout,
      maxBuffer: 10 * 1024 * 1024, // 10 MB
      cwd: workdir,
      shell: detectShell(),
    };

    const child = exec(command, options, (error, stdout, stderr) => {
      if (error) {
        // exec error — non-zero exit or timeout
        const errAny = error as { code?: number; killed?: boolean; message: string };
        resolve(
          JSON.stringify({
            exitCode: errAny.code ?? 1,
            stdout: stdout || '',
            stderr: stderr || '',
            killed: errAny.killed ?? false,
            error: error.message,
          }),
        );
      } else {
        resolve(
          JSON.stringify({
            exitCode: 0,
            stdout,
            stderr,
          }),
        );
      }
    });

    // If no response within timeout, kill the process
    const killTimer = setTimeout(() => {
      child.kill('SIGTERM');
      // Give it a moment, then force kill
      setTimeout(() => {
        if (!child.killed) {
          child.kill('SIGKILL');
        }
      }, 2000);
    }, timeout);

    child.on('close', () => clearTimeout(killTimer));
  });
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
