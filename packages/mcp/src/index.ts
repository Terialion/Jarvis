// ============================================================================
// @jarvis/mcp — MCP server, client, and transport abstractions
// ============================================================================

export { MCPServer } from './server.js';
export { MCPClient } from './client.js';
export { StdioMCPTransport } from './stdio-transport.js';
export { connectMcpServers } from './manager.js';
export type { McpServerConfig, McpConnectionState, McpConnectionStatus } from './manager.js';
export type {
  JsonRpcRequest,
  JsonRpcResponse,
  JsonRpcError,
  MCPToolDefinition,
  MCPResourceDefinition,
  MCPPromptDefinition,
  MCPServerInfo,
  MCPConnection,
  MCPTransport,
  MCPToolHandler,
} from './models.js';
