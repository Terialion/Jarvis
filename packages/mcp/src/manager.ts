import { MCPClient } from './client.js';
import { StdioMCPTransport } from './stdio-transport.js';

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

function shouldRetryWithNpxFallback(server: { config: McpServerConfig }, errorMessage: string): boolean {
  const command = server.config.command.trim().toLowerCase();
  const args = server.config.args ?? [];
  return (
    command === 'pnpm' &&
    args.length >= 2 &&
    args[0] === 'dlx' &&
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
      const transport = new StdioMCPTransport(
        server.config.command,
        server.config.args ?? [],
        server.config.cwd,
        server.config.env,
      );
      const conn = await client.connect(transport);
      status.state = conn.tools.length > 0 || conn.resources.length > 0 ? 'ready' : 'degraded';
      status.serverName = conn.serverInfo?.name ?? server.id;
      status.toolCount = conn.tools.length;
      status.resourceCount = conn.resources.length;
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
