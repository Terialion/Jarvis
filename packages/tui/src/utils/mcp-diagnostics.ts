import type { MCPClient, McpConnectionStatus, McpServerConfig } from '@jarvis/mcp';
import { MCPClient as MCPClientClass, connectMcpServers } from '@jarvis/mcp';
import type { SlashCommandCtx } from '../commands/types.js';

export function formatMcpDiagnostics(
  configured: Array<{ id: string; plugin?: string; config: McpServerConfig }>,
  statuses: McpConnectionStatus[],
  client: MCPClient | null,
): string {
  const lines: string[] = ['MCP diagnostics:\n'];
  lines.push(`Configured servers: ${configured.length}`);
  lines.push(`Connected servers: ${client?.connections.length ?? 0}`);
  lines.push('');

  if (configured.length > 0) {
    lines.push('Configured:');
    lines.push('  ID                   Source        Command');
    lines.push('  -------------------- ------------- ------------------------------');
    for (const entry of configured) {
      const id = entry.id.padEnd(20, ' ').slice(0, 20);
      const source = (entry.plugin ?? 'user').padEnd(13, ' ').slice(0, 13);
      const cmd = (entry.config.command ?? '').slice(0, 30);
      lines.push(`  ${id} ${source} ${cmd}`);
    }
    lines.push('');
  }

  if (statuses.length > 0) {
    lines.push('Connection status:');
    lines.push('  ID                   State       Server                  Tools  Resources');
    lines.push('  -------------------- ----------- ----------------------- ------ ---------');
    for (const status of statuses) {
      const id = status.id.padEnd(20, ' ').slice(0, 20);
      const state = status.state.padEnd(11, ' ').slice(0, 11);
      const server = (status.serverName ?? '-').padEnd(23, ' ').slice(0, 23);
      const tools = String(status.toolCount ?? 0).padStart(6, ' ');
      const resources = String(status.resourceCount ?? 0).padStart(9, ' ');
      lines.push(`  ${id} ${state} ${server} ${tools} ${resources}`);
      if (status.error) lines.push(`    error: ${status.error}`);
    }
  } else {
    lines.push('No connection status available yet. Start a new turn or restart Jarvis after config changes.');
  }

  return lines.join('\n');
}

export async function refreshMcpStatuses(
  ctx: Pick<SlashCommandCtx, 'mcpClientRef' | 'mcpConfiguredRef' | 'mcpStatusesRef'>,
): Promise<McpConnectionStatus[]> {
  if (!ctx.mcpClientRef.current) {
    ctx.mcpClientRef.current = new MCPClientClass();
  }
  const configured = ctx.mcpConfiguredRef.current;
  if (configured.length === 0) {
    ctx.mcpStatusesRef.current = [];
    return [];
  }
  ctx.mcpClientRef.current.disconnectAll();
  const statuses = await connectMcpServers(ctx.mcpClientRef.current, configured);
  ctx.mcpStatusesRef.current = statuses;
  return statuses;
}
