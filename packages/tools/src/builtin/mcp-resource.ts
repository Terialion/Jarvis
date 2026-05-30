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

// ---- mcp_status ----

export const mcpStatusSchema = toOpenAITool({
  name: 'mcp_status',
  description:
    'Show MCP connection status, including connected servers and exposed capability counts.',
  parameters: {
    type: 'object',
    properties: {},
  },
});

export const mcpHealthcheckSchema = toOpenAITool({
  name: 'mcp_healthcheck',
  description:
    'One-shot MCP health check: combines status and resource snapshot for connected servers.',
  parameters: {
    type: 'object',
    properties: {
      maxResourcesPerServer: {
        type: 'number',
        description: 'Optional cap per server for resource previews (default 5).',
      },
    },
  },
});

export function createMcpStatusHandler(client: McpResourceClient): ToolHandler {
  return (_args: Record<string, unknown>, _context: ToolContext): string => {
    const servers = client.connections.map((conn) => ({
      name: conn.serverInfo?.name ?? 'unknown',
      version: conn.serverInfo?.version ?? '',
      resources: Array.isArray(conn.resources) ? conn.resources.length : 0,
    }));

    return JSON.stringify({
      connected: servers.length > 0,
      serverCount: servers.length,
      servers,
      message:
        servers.length > 0
          ? `Connected to ${servers.length} MCP server(s).`
          : 'No MCP servers connected. Configure and connect servers before using MCP tools/resources.',
    });
  };
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

export function createMcpHealthcheckHandler(client: McpResourceClient): ToolHandler {
  return (args: Record<string, unknown>, _context: ToolContext): string => {
    const maxResourcesPerServer =
      typeof args.maxResourcesPerServer === 'number' && Number.isFinite(args.maxResourcesPerServer)
        ? Math.max(1, Math.floor(args.maxResourcesPerServer))
        : 5;

    const servers = client.connections.map((conn) => {
      const name = conn.serverInfo?.name ?? 'unknown';
      const version = conn.serverInfo?.version ?? '';
      const resources = Array.isArray(conn.resources) ? conn.resources : [];
      return {
        name,
        version,
        resourceCount: resources.length,
        resourcesPreview: resources.slice(0, maxResourcesPerServer).map((resource) => ({
          uri: resource.uri,
          name: resource.name,
          mimeType: resource.mimeType ?? 'text/plain',
        })),
        previewOverflow: Math.max(0, resources.length - maxResourcesPerServer),
      };
    });

    return JSON.stringify({
      ok: true,
      connected: servers.length > 0,
      serverCount: servers.length,
      servers,
      message:
        servers.length > 0
          ? `MCP healthy: connected to ${servers.length} server(s).`
          : 'No MCP servers connected.',
      suggestions:
        servers.length > 0
          ? []
          : [
              'Run plugin_bootstrap or mcp_bootstrap to configure a server.',
              'Restart Jarvis and run mcp_status again.',
            ],
    });
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

export function createMcpStatusTool(client: McpResourceClient): ToolEntry {
  return {
    name: 'mcp_status',
    toolset: 'mcp',
    schema: mcpStatusSchema,
    handler: createMcpStatusHandler(client),
    isAsync: false,
    emoji: '🧭',
    maxResultSizeChars: 30_000,
  };
}

export function createMcpHealthcheckTool(client: McpResourceClient): ToolEntry {
  return {
    name: 'mcp_healthcheck',
    toolset: 'mcp',
    schema: mcpHealthcheckSchema,
    handler: createMcpHealthcheckHandler(client),
    isAsync: false,
    emoji: '🩺',
    maxResultSizeChars: 50_000,
  };
}
