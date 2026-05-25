// ============================================================================
// MCP resource tools — list and read resources from MCP servers
// Factory pattern: accepts MCP client reference at creation time
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';

// ---- minimal MCP client interface ----

export interface McpResourceClient {
  connections: Array<{
    serverInfo: { name: string; version: string } | null;
    resources: Array<{ uri: string; name: string; description?: string; mimeType?: string; server?: string }>;
  }>;
  readResource(connection: McpResourceClient['connections'][number], uri: string): Promise<unknown>;
}

// ---- list_mcp_resources ----

export const listMcpResourcesSchema = toOpenAITool({
  name: 'list_mcp_resources',
  description:
    'List available resources from connected MCP servers. Each resource includes its URI, name, description, and MIME type. Optionally filter by server name.',
  parameters: {
    type: 'object',
    properties: {
      server: {
        type: 'string',
        description: 'Optional server name to filter resources by.',
      },
    },
  },
});

export function createListMcpResourcesHandler(client: McpResourceClient): ToolHandler {
  return (_args: Record<string, unknown>, _context: ToolContext): string => {
    const serverFilter = typeof _args.server === 'string' ? _args.server.trim() : undefined;

    const allResources: Array<Record<string, unknown>> = [];

    for (const conn of client.connections) {
      const serverName = conn.serverInfo?.name ?? 'unknown';
      if (serverFilter && serverName !== serverFilter) continue;

      for (const resource of conn.resources) {
        allResources.push({
          server: serverName,
          uri: resource.uri,
          name: resource.name,
          description: resource.description ?? '',
          mimeType: resource.mimeType ?? 'text/plain',
        });
      }
    }

    if (allResources.length === 0) {
      return JSON.stringify({
        resources: [],
        message: serverFilter
          ? `No resources found for server "${serverFilter}".`
          : 'No MCP resources available. Connect an MCP server first.',
      });
    }

    return JSON.stringify({ resources: allResources });
  };
}

// ---- read_mcp_resource ----

export const readMcpResourceSchema = toOpenAITool({
  name: 'read_mcp_resource',
  description:
    'Read a specific resource from an MCP server, identified by server name and resource URI.',
  parameters: {
    type: 'object',
    properties: {
      server: {
        type: 'string',
        description: 'The MCP server name.',
      },
      uri: {
        type: 'string',
        description: 'The resource URI to read.',
      },
    },
    required: ['server', 'uri'],
  },
});

export function createReadMcpResourceHandler(client: McpResourceClient): ToolHandler {
  return async (args: Record<string, unknown>, _context: ToolContext): Promise<string> => {
    const server = String(args.server ?? '').trim();
    const uri = String(args.uri ?? '').trim();

    if (!server || !uri) {
      return JSON.stringify({ error: 'Missing required parameters: server and uri' });
    }

    const conn = client.connections.find(
      (c) => (c.serverInfo?.name ?? 'unknown') === server,
    );

    if (!conn) {
      return JSON.stringify({
        error: `MCP server "${server}" not found. Available servers: ${client.connections.map((c) => c.serverInfo?.name ?? 'unknown').join(', ')}`,
      });
    }

    try {
      const result = await client.readResource(conn, uri);
      return JSON.stringify({ server, uri, content: result });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: `MCP resource read failed: ${message}` });
    }
  };
}

// ---- factories ----

export function createListMcpResourcesTool(client: McpResourceClient): ToolEntry {
  return {
    name: 'list_mcp_resources',
    toolset: 'mcp',
    schema: listMcpResourcesSchema,
    handler: createListMcpResourcesHandler(client),
    isAsync: false,
    emoji: '📋',
    maxResultSizeChars: 50_000,
  };
}

export function createReadMcpResourceTool(client: McpResourceClient): ToolEntry {
  return {
    name: 'read_mcp_resource',
    toolset: 'mcp',
    schema: readMcpResourceSchema,
    handler: createReadMcpResourceHandler(client),
    isAsync: true,
    emoji: '📄',
    maxResultSizeChars: 100_000,
  };
}
