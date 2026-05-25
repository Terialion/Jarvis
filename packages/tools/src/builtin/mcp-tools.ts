// ============================================================================
// MCP tools — dynamically expose MCP server tools as LLM-callable ToolEntry
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- minimal MCP client interface (avoids coupling to @jarvis/mcp) ----

export interface McpToolClient {
  connections: Array<{
    serverInfo: { name: string; version: string } | null;
    tools: Array<{ name: string; description: string; inputSchema: Record<string, unknown> }>;
  }>;
  callTool(
    connection: McpToolClient['connections'][number],
    toolName: string,
    args: Record<string, unknown>,
  ): Promise<unknown>;
}

// ---- factory ----

/** Convert all MCP server tools to ToolEntry[] for LLM tool discovery. */
export function createMcpToolEntries(client: McpToolClient): ToolEntry[] {
  const entries: ToolEntry[] = [];

  for (const conn of client.connections) {
    const serverName = conn.serverInfo?.name ?? 'unknown';

    for (const tool of conn.tools) {
      // Namespace: mcp__server__toolName (matches Claude Code convention)
      const mcpName = `mcp__${serverName}__${tool.name}`;

      const schema = toOpenAITool({
        name: mcpName,
        description: `[MCP:${serverName}] ${tool.description}`,
        parameters: {
          type: 'object',
          properties: (tool.inputSchema.properties as Record<string, unknown>) ?? {},
          required: (tool.inputSchema.required as string[]) ?? [],
        },
      });

      const handler: ToolHandler = async (args, _context) => {
        const result = await client.callTool(conn, tool.name, args);
        return JSON.stringify({
          server: serverName,
          tool: tool.name,
          result,
        });
      };

      entries.push({
        name: mcpName,
        toolset: 'mcp',
        schema,
        handler,
        isAsync: true,
        emoji: '🔌',
        maxResultSizeChars: 50_000,
      });
    }
  }

  return entries;
}
