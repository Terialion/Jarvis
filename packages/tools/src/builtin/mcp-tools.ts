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
    serverName?: string;
  }>;
  callTool(
    connection: McpToolClient['connections'][number],
    toolName: string,
    args: Record<string, unknown>,
  ): Promise<unknown>;
}

// ---- circuit breaker (per-server) ----

const FAILURE_THRESHOLD = 3;
const COOLDOWN_MS = 60_000;
const serverCircuits = new Map<string, { failures: number; openedAt: number }>();

function checkCircuit(serverId: string): string | null {
  const c = serverCircuits.get(serverId);
  if (!c || c.failures < FAILURE_THRESHOLD) return null;
  const elapsed = Date.now() - c.openedAt;
  if (elapsed >= COOLDOWN_MS) {
    serverCircuits.delete(serverId);
    return null;
  }
  return `MCP server "${serverId}" circuit breaker open (${FAILURE_THRESHOLD} failures). Retry in ${Math.ceil((COOLDOWN_MS - elapsed) / 1000)}s`;
}

function recordSuccess(serverId: string): void {
  serverCircuits.delete(serverId);
}

function recordFailure(serverId: string): void {
  const existing = serverCircuits.get(serverId);
  const failures = (existing?.failures ?? 0) + 1;
  serverCircuits.set(serverId, { failures, openedAt: Date.now() });
}

// ---- prompt injection scan ----

const INJECTION_PATTERNS = [
  /ignore\s+(previous|prior|above)\s+(instructions|prompts?)/i,
  /disregard\s+(previous|prior|all)\s+(instructions|prompts?)/i,
  /you\s+are\s+now\s+a/i,
  /system\s*:\s*/i,
  /\[INST\]/i,
  /<<SYS>>/i,
];

function scanForInjection(text: string, toolName: string): void {
  for (const pattern of INJECTION_PATTERNS) {
    if (pattern.test(text)) {
      console.warn(`[MCP] Prompt injection pattern detected in tool "${toolName}": ${pattern.source}`);
      break;
    }
  }
}

// ---- description truncation ----

const MAX_DESCRIPTION_LENGTH = 1200;

function sanitizeDescription(desc: string, toolName: string): string {
  scanForInjection(desc, toolName);
  if (desc.length > MAX_DESCRIPTION_LENGTH) {
    return desc.slice(0, MAX_DESCRIPTION_LENGTH) + '…';
  }
  return desc;
}

// ---- factory ----

export interface McpToolFilterConfig {
  /** Only include these tools (glob patterns supported) */
  include?: string[];
  /** Exclude these tools (glob patterns supported) */
  exclude?: string[];
}

// ---- tool name sanitization (reference: OpenClaw/Codex) ----
function sanitizeToolName(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
}

function matchesFilter(name: string, patterns: string[]): boolean {
  return patterns.some((p) => {
    if (p.includes('*') || p.includes('?')) {
      const regex = new RegExp('^' + p.replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
      return regex.test(name);
    }
    return name === p;
  });
}

/** Convert all MCP server tools to ToolEntry[] for LLM tool discovery. */
export function createMcpToolEntries(
  client: McpToolClient,
  toolFilters?: Map<string, McpToolFilterConfig>,
): ToolEntry[] {
  const entries: ToolEntry[] = [];

  for (const conn of client.connections) {
    const serverId = conn.serverName ?? conn.serverInfo?.name ?? 'unknown';
    const serverName = conn.serverInfo?.name ?? serverId;
    const filter = toolFilters?.get(serverId);

    for (const tool of conn.tools) {
      // Apply tool filtering
      if (filter?.include && !matchesFilter(tool.name, filter.include)) continue;
      if (filter?.exclude && matchesFilter(tool.name, filter.exclude)) continue;

      // Namespace: mcp__server__toolName (matches Claude Code convention)
      const safeServer = sanitizeToolName(serverName);
      const safeTool = sanitizeToolName(tool.name);
      const mcpName = `mcp__${safeServer}__${safeTool}`;

      const description = sanitizeDescription(tool.description ?? '', tool.name);

      const schema = toOpenAITool({
        name: mcpName,
        description: `[MCP:${serverName}] ${description}`,
        parameters: {
          type: 'object',
          properties: (tool.inputSchema.properties as Record<string, unknown>) ?? {},
          required: (tool.inputSchema.required as string[]) ?? [],
        },
      });

      const handler: ToolHandler = async (args, _context) => {
        // Circuit breaker check
        const blocked = checkCircuit(serverId);
        if (blocked) {
          return JSON.stringify({ error: blocked });
        }

        try {
          const result = await client.callTool(conn, tool.name, args);
          recordSuccess(serverId);
          return JSON.stringify({
            server: serverName,
            tool: tool.name,
            result,
          });
        } catch (error) {
          recordFailure(serverId);
          throw error;
        }
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
