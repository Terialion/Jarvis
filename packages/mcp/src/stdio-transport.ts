import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import type { JsonRpcRequest, JsonRpcResponse, MCPTransport } from './models.js';

type Pending = {
  resolve: (value: JsonRpcResponse) => void;
  reject: (error: Error) => void;
};

// ---- Global process tracking for cleanup on exit ----
const allChildren = new Set<{ pid: number; kill: () => void }>();

function registerChild(child: ChildProcessWithoutNullStreams): void {
  const entry = { pid: child.pid ?? 0, kill: () => { try { child.kill(); } catch {} } };
  allChildren.add(entry);
  child.on('close', () => allChildren.delete(entry));
}

// Cleanup all MCP child processes on process exit
function cleanupAll(): void {
  for (const entry of allChildren) {
    try { entry.kill(); } catch {}
  }
}
process.on('exit', cleanupAll);
process.on('SIGINT', () => { cleanupAll(); process.exit(130); });
process.on('SIGTERM', () => { cleanupAll(); process.exit(143); });

// ---- stderr logging ----
function getLogDir(): string {
  const home = process.env['HOME'] ?? process.env['USERPROFILE'] ?? '/tmp';
  return join(home, '.jarvis', 'logs');
}

function logStderr(serverId: string, data: string): void {
  try {
    const dir = getLogDir();
    mkdirSync(dir, { recursive: true });
    const logFile = join(dir, 'mcp-stderr.log');
    const timestamp = new Date().toISOString();
    appendFileSync(logFile, `[${timestamp}] [${serverId}] ${data}\n`, 'utf8');
  } catch {
    // best-effort logging
  }
}

/**
 * Minimal newline-delimited JSON-RPC stdio transport for common MCP servers.
 * Many popular MCP servers (filesystem/memory) support this framing mode.
 */
export class StdioMCPTransport implements MCPTransport {
  private child: ChildProcessWithoutNullStreams;
  private pending = new Map<string | number, Pending>();
  private buffer = '';
  private closed = false;
  private serverId: string;

  constructor(command: string, args: string[] = [], cwd?: string, env?: Record<string, string>, serverId?: string) {
    this.serverId = serverId ?? command;
    const launch = this.resolveSpawnTarget(command, args, env);
    this.child = spawn(launch.command, launch.args, {
      cwd,
      env: env ?? process.env,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: false,
      // Windows: create new process group for clean termination
      ...(process.platform === 'win32' ? { windowsHide: true } : {}),
    });

    registerChild(this.child);

    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', (chunk: string) => {
      this.buffer += chunk;
      this.drainLines();
    });

    // Redirect stderr to log file (not TUI)
    this.child.stderr.setEncoding('utf8');
    this.child.stderr.on('data', (chunk: string) => {
      logStderr(this.serverId, chunk);
    });

    this.child.on('error', (error) => {
      this.failAll(new Error(`MCP process error: ${error.message}`));
    });

    this.child.on('close', (code) => {
      this.closed = true;
      this.failAll(new Error(`MCP process exited with code ${code ?? -1}`));
    });
  }

  private resolveSpawnTarget(
    command: string,
    args: string[],
    env?: Record<string, string>,
  ): { command: string; args: string[] } {
    if (process.platform !== 'win32') {
      return { command, args };
    }

    const resolved = this.resolveWindowsCommand(command, env);
    if (resolved.toLowerCase().endsWith('.ps1')) {
      return {
        command: 'powershell.exe',
        args: ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', resolved, ...args],
      };
    }

    // Windows .cmd/.bat files cannot be spawned directly — wrap with cmd.exe /c
    if (resolved.toLowerCase().endsWith('.cmd') || resolved.toLowerCase().endsWith('.bat')) {
      return {
        command: 'cmd.exe',
        args: ['/d', '/c', resolved, ...args],
      };
    }

    return { command: resolved, args };
  }

  private resolveWindowsCommand(command: string, env?: Record<string, string>): string {
    const candidateExts = ['', '.cmd', '.exe', '.bat', '.ps1'];
    const commandLower = command.toLowerCase();
    const hasExt = candidateExts.slice(1).some((ext) => commandLower.endsWith(ext));
    const attempts: string[] = [];

    const check = (candidate: string): string | null => {
      attempts.push(candidate);
      return existsSync(candidate) ? candidate : null;
    };

    if (command.includes('\\') || command.includes('/')) {
      if (hasExt) {
        const found = check(command);
        if (found) return found;
      }
      for (const ext of candidateExts.slice(1)) {
        const found = check(`${command}${ext}`);
        if (found) return found;
      }
    } else {
      const mergedEnv = env ? { ...process.env, ...env } : process.env;
      const pathValue = mergedEnv.PATH ?? mergedEnv.Path ?? '';
      const pathDirs = pathValue.split(delimiter).filter(Boolean);
      // On Windows, spawn needs .cmd/.exe — prefer those over extensionless binaries
      const searchExts = hasExt ? [''] : ['.cmd', '.exe', '.bat', '.ps1', ''];
      for (const dir of pathDirs) {
        for (const ext of searchExts) {
          const suffix = ext || '';
          const found = check(`${dir}\\${command}${suffix}`);
          if (found) return found;
        }
      }
    }

    throw new Error(
      `MCP command not found on Windows: "${command}". Tried: ${attempts.slice(0, 12).join(', ')}`,
    );
  }

  async send(message: JsonRpcRequest): Promise<JsonRpcResponse> {
    if (this.closed) {
      throw new Error('MCP transport is closed');
    }

    return new Promise<JsonRpcResponse>((resolve, reject) => {
      this.pending.set(message.id, { resolve, reject });
      try {
        this.child.stdin.write(`${JSON.stringify(message)}\n`);
      } catch (error) {
        this.pending.delete(message.id);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;

    const pid = this.child.pid;

    if (process.platform === 'win32') {
      // Windows: use taskkill to kill process tree
      try {
        if (pid) {
          const { execSync } = require('node:child_process');
          execSync(`taskkill /PID ${pid} /T /F`, { stdio: 'ignore' });
        }
      } catch {
        // fallback: direct kill
        try { this.child.kill(); } catch {}
      }
    } else {
      // Unix: SIGTERM first, then SIGKILL after 2s grace period
      try {
        if (pid) {
          process.kill(-pid, 'SIGTERM'); // kill process group
        }
      } catch {
        try { this.child.kill('SIGTERM'); } catch {}
      }

      const forceTimer = setTimeout(() => {
        try {
          if (pid) {
            process.kill(-pid, 'SIGKILL');
          }
        } catch {
          try { this.child.kill('SIGKILL'); } catch {}
        }
      }, 2000);

      // Don't keep the event loop alive just for the force-kill timer
      if (forceTimer.unref) forceTimer.unref();
    }

    this.failAll(new Error('MCP transport closed'));
  }

  private drainLines(): void {
    while (true) {
      const nl = this.buffer.indexOf('\n');
      if (nl === -1) return;
      const line = this.buffer.slice(0, nl).trim();
      this.buffer = this.buffer.slice(nl + 1);
      if (!line) continue;

      let parsed: JsonRpcResponse | null = null;
      try {
        parsed = JSON.parse(line) as JsonRpcResponse;
      } catch {
        continue;
      }
      if (!parsed || parsed.id === undefined || parsed.id === null) continue;
      const pending = this.pending.get(parsed.id);
      if (!pending) continue;
      this.pending.delete(parsed.id);
      pending.resolve(parsed);
    }
  }

  private failAll(error: Error): void {
    for (const [, pending] of this.pending) {
      pending.reject(error);
    }
    this.pending.clear();
  }
}
