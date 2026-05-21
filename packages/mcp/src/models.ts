// ============================================================================
// MCP models — JSON-RPC types and MCP protocol types
// ============================================================================

// ============================================================================
// JSON-RPC 2.0
// ============================================================================

export interface JsonRpcRequest {
  jsonrpc: '2.0';
  id: string | number;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcResponse {
  jsonrpc: '2.0';
  id: string | number;
  result?: unknown;
  error?: JsonRpcError;
}

export interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
}

// ============================================================================
// MCP Server Capabilities
// ============================================================================

export interface MCPToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export interface MCPResourceDefinition {
  uri: string;
  name: string;
  description?: string;
  mimeType?: string;
}

export interface MCPPromptDefinition {
  name: string;
  description?: string;
  arguments?: Array<{
    name: string;
    description?: string;
    required?: boolean;
  }>;
}

// ============================================================================
// MCP Client types
// ============================================================================

export interface MCPServerInfo {
  name: string;
  version: string;
  protocolVersion?: string;
}

export interface MCPConnection {
  transport: MCPTransport;
  serverInfo: MCPServerInfo;
  tools: MCPToolDefinition[];
  resources: MCPResourceDefinition[];
  prompts: MCPPromptDefinition[];
}

// ============================================================================
// Transport
// ============================================================================

export interface MCPTransport {
  /** Send a JSON-RPC request and return the response */
  send(message: JsonRpcRequest): Promise<JsonRpcResponse>;
  /** Close the transport */
  close(): void;
}

// ============================================================================
// Tool handler on server side
// ============================================================================

export type MCPToolHandler = (
  args: Record<string, unknown>,
) => Promise<{ content: Array<{ type: string; text: string }> }>;
