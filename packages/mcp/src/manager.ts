import { MCPClient } from './client.js';
import { StdioMCPTransport } from './stdio-transport.js';
import { execSync } from 'node:child_process';

export type McpServerConfig = {
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
};

export type McpConnectionState = 'connecting' | 'ready' | 'degraded' | 'retrying' | 'failed';

export type McpConnectionStatus = {
  id: string;
  plugin?: string;
  state: McpConnectionState;
  serverName?: string;
  toolCount?: number;
  resourceCount?: number;
  error?: string;
};

function isPnpmLikeCommand(command: string): boolean {
  const normalized = command.trim().toLowerCase().replace(/\\/g, '/');
  return (
    normalized === 'pnpm'
    || normalized.endsWith('/pnpm')
    || normalized.endsWith('/pnpm.cmd')
    || normalized.endsWith('/pnpm.exe')
  );
}

function shouldRetryWithNpxFallback(server: { config: McpServerConfig }, errorMessage: string): boolean {
  const command = server.config.command.trim();
  const args = server.config.args ?? [];
  return (
    isPnpmLikeCommand(command) &&
    args.length >= 2 &&
    String(args[0]).toLowerCase() === 'dlx' &&
    errorMessage.includes('ENOENT')
  );
}

function toNpxFallbackConfig(config: McpServerConfig): McpServerConfig {
  const args = config.args ?? [];
  const pkg = args[1] ?? '';
  const rest = args.slice(2);
  return {
    ...config,
    command: 'npx',
    args: ['-y', pkg, ...rest],
  };
}

function canResolveCommand(command: string): boolean {
  try {
    if (process.platform === 'win32') {
      const escaped = command.replace(/"/g, '\\"');
      const out = execSync(`where "${escaped}"`, { encoding: 'utf8' }).trim();
      return out.length > 0;
    }
    const out = execSync(`command -v ${command}`, { encoding: 'utf8', shell: '/bin/sh' }).trim();
    return out.length > 0;
  } catch {
    return false;
  }
}

function normalizeConfigForPlatform(config: McpServerConfig): { config: McpServerConfig; normalized: boolean; note?: string } {
  if (process.platform !== 'win32') {
    return { config, normalized: false };
  }
  const args = config.args ?? [];
  if (!isPnpmLikeCommand(config.command) || args.length < 2 || String(args[0]).toLowerCase() !== 'dlx') {
    return { config, normalized: false };
  }
  // On Windows, plugin configs frequently reference pnpm paths that are missing.
  // Prefer npx fallback up-front when pnpm cannot be resolved.
  if (!canResolveCommand('pnpm')) {
    return {
      config: toNpxFallbackConfig(config),
      normalized: true,
      note: 'pnpm not found on PATH; switched to npx fallback',
    };
  }
  return { config, normalized: false };
}

export async function connectMcpServers(
  client: MCPClient,
  servers: Array<{ id: string; plugin?: string; config: McpServerConfig }>,
): Promise<McpConnectionStatus[]> {
  const statuses: McpConnectionStatus[] = [];
  for (const server of servers) {
    const status: McpConnectionStatus = {
      id: server.id,
      plugin: server.plugin,
      state: 'connecting',
    };
    statuses.push(status);

    try {
      const normalized = normalizeConfigForPlatform(server.config);
      const transport = new StdioMCPTransport(
        normalized.config.command,
        normalized.config.args ?? [],
        normalized.config.cwd,
        normalized.config.env,
      );
      const conn = await client.connect(transport);
      status.state = conn.tools.length > 0 || conn.resources.length > 0 ? 'ready' : 'degraded';
      status.serverName = conn.serverInfo?.name ?? server.id;
      status.toolCount = conn.tools.length;
      status.resourceCount = conn.resources.length;
      if (normalized.normalized && normalized.note) {
        status.error = normalized.note;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (shouldRetryWithNpxFallback(server, message)) {
        status.state = 'retrying';
        try {
          const fallback = toNpxFallbackConfig(server.config);
          const transport = new StdioMCPTransport(
            fallback.command,
            fallback.args ?? [],
            fallback.cwd,
            fallback.env,
          );
          const conn = await client.connect(transport);
          status.state = conn.tools.length > 0 || conn.resources.length > 0 ? 'ready' : 'degraded';
          status.serverName = conn.serverInfo?.name ?? server.id;
          status.toolCount = conn.tools.length;
          status.resourceCount = conn.resources.length;
          status.error = 'Recovered from pnpm ENOENT via npx fallback';
          continue;
        } catch (retryError) {
          const retryMessage = retryError instanceof Error ? retryError.message : String(retryError);
          status.state = 'failed';
          status.error = `${message}; npx fallback failed: ${retryMessage}`;
          continue;
        }
      }
      status.state = 'failed';
      status.error = message;
    }
  }
  return statuses;
}
