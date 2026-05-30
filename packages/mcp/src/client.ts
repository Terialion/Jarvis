// ============================================================================
// MCPClient — connect to external MCP servers via stdio transport
// ============================================================================

import type {
  JsonRpcRequest,
  JsonRpcResponse,
  MCPConnection,
  MCPServerInfo,
  MCPToolDefinition,
  MCPResourceDefinition,
  MCPPromptDefinition,
  MCPTransport,
} from './models.js';

// ============================================================================
// MCPClient
// ============================================================================

export class MCPClient {
  private _connections: MCPConnection[] = [];
  private nextId = 1;

  /** View of active MCP connections (for resource listing tools). */
  get connections(): MCPConnection[] {
    return this._connections;
  }

  // ========================================================================
  // Connection management
  // ========================================================================

  /**
   * Connect to an MCP server using the provided transport.
   * Performs the MCP initialize handshake and discovers capabilities.
   */
  async connect(transport: MCPTransport): Promise<MCPConnection> {
    // Initialize handshake
    const initResponse = await transport.send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'initialize',
      params: {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: { name: 'jarvis', version: '0.1.0' },
      },
    });

    if (initResponse.error) {
      throw new Error(
        `MCP initialize failed: ${initResponse.error.message}`,
      );
    }

    const serverInfo: MCPServerInfo = (initResponse.result as Record<string, unknown>)
      ?.serverInfo as MCPServerInfo;

    // Discover tools
    const toolsResponse = await transport.send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'tools/list',
    });

    const tools: MCPToolDefinition[] = toolsResponse.error
      ? []
      : ((toolsResponse.result as Record<string, unknown>)?.tools as MCPToolDefinition[]) ?? [];

    // Discover resources
    const resourcesResponse = await transport.send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'resources/list',
    });

    const resources: MCPResourceDefinition[] = resourcesResponse.error
      ? []
      : ((resourcesResponse.result as Record<string, unknown>)
          ?.resources as MCPResourceDefinition[]) ?? [];

    // Discover prompts
    const promptsResponse = await transport.send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'prompts/list',
    });

    const prompts: MCPPromptDefinition[] = promptsResponse.error
      ? []
      : ((promptsResponse.result as Record<string, unknown>)
          ?.prompts as MCPPromptDefinition[]) ?? [];

    const connection: MCPConnection = {
      transport,
      serverInfo,
      tools,
      resources,
      prompts,
    };

    this._connections.push(connection);
    return connection;
  }

  // ========================================================================
  // Tool operations
  // ========================================================================

  async listTools(connection: MCPConnection): Promise<MCPToolDefinition[]> {
    return connection.tools;
  }

  async callTool(
    connection: MCPConnection,
    toolName: string,
    args: Record<string, unknown> = {},
  ): Promise<unknown> {
    const response = await connection.transport.send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'tools/call',
      params: { name: toolName, arguments: args },
    });

    if (response.error) {
      throw new Error(`MCP tool call failed: ${response.error.message}`);
    }

    return response.result;
  }

  // ========================================================================
  // Resource operations
  // ========================================================================

  async listResources(connection: MCPConnection): Promise<MCPResourceDefinition[]> {
    return connection.resources;
  }

  async readResource(
    connection: MCPConnection,
    uri: string,
  ): Promise<unknown> {
    const response = await connection.transport.send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'resources/read',
      params: { uri },
    });

    if (response.error) {
      throw new Error(`MCP resource read failed: ${response.error.message}`);
    }

    return response.result;
  }

  // ========================================================================
  // Prompt operations
  // ========================================================================

  async listPrompts(connection: MCPConnection): Promise<MCPPromptDefinition[]> {
    return connection.prompts;
  }

  async getPrompt(
    connection: MCPConnection,
    promptName: string,
    args?: Record<string, unknown>,
  ): Promise<unknown> {
    const response = await connection.transport.send({
      jsonrpc: '2.0',
      id: this.nextId++,
      method: 'prompts/get',
      params: { name: promptName, arguments: args },
    });

    if (response.error) {
      throw new Error(`MCP prompt get failed: ${response.error.message}`);
    }

    return response.result;
  }

  // ========================================================================
  // Cleanup
  // ========================================================================

  disconnect(connection: MCPConnection): void {
    connection.transport.close();
    const idx = this._connections.indexOf(connection);
    if (idx !== -1) this._connections.splice(idx, 1);
  }

  disconnectAll(): void {
    for (const conn of this._connections) {
      conn.transport.close();
    }
    this._connections = [];
  }
}
