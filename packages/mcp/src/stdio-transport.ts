import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync } from 'node:fs';
import { delimiter } from 'node:path';
import type { JsonRpcRequest, JsonRpcResponse, MCPTransport } from './models.js';

type Pending = {
  resolve: (value: JsonRpcResponse) => void;
  reject: (error: Error) => void;
};

/**
 * Minimal newline-delimited JSON-RPC stdio transport for common MCP servers.
 * Many popular MCP servers (filesystem/memory) support this framing mode.
 */
export class StdioMCPTransport implements MCPTransport {
  private child: ChildProcessWithoutNullStreams;
  private pending = new Map<string | number, Pending>();
  private buffer = '';
  private closed = false;

  constructor(command: string, args: string[] = [], cwd?: string, env?: Record<string, string>) {
    const launch = this.resolveSpawnTarget(command, args, env);
    this.child = spawn(launch.command, launch.args, {
      cwd,
      env: env ? { ...process.env, ...env } : process.env,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: false,
    });

    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', (chunk: string) => {
      this.buffer += chunk;
      this.drainLines();
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
      for (const dir of pathDirs) {
        for (const ext of hasExt ? [''] : candidateExts) {
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
    try {
      this.child.kill();
    } catch {
      // ignore close failures
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
