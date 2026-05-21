// ============================================================================
// MCPServer — JSON-RPC gateway for serving tools/resources/prompts
// ============================================================================

import type {
  JsonRpcRequest,
  JsonRpcResponse,
  MCPToolDefinition,
  MCPResourceDefinition,
  MCPPromptDefinition,
  MCPToolHandler,
} from './models.js';

// ============================================================================
// MCPServer
// ============================================================================

export class MCPServer {
  private tools: Map<string, { definition: MCPToolDefinition; handler: MCPToolHandler }> =
    new Map();
  private resources: MCPResourceDefinition[] = [];
  private prompts: MCPPromptDefinition[] = [];
  private promptHandlers: Map<
    string,
    (args?: Record<string, unknown>) => Promise<{ messages: unknown[] }>
  > = new Map();

  // ========================================================================
  // Registration
  // ========================================================================

  registerTool(
    definition: MCPToolDefinition,
    handler: MCPToolHandler,
  ): void {
    this.tools.set(definition.name, { definition, handler });
  }

  registerResource(resource: MCPResourceDefinition): void {
    this.resources.push(resource);
  }

  registerPrompt(
    definition: MCPPromptDefinition,
    handler: (args?: Record<string, unknown>) => Promise<{ messages: unknown[] }>,
  ): void {
    this.prompts.push(definition);
    this.promptHandlers.set(definition.name, handler);
  }

  // ========================================================================
  // JSON-RPC dispatch
  // ========================================================================

  /**
   * Process a single JSON-RPC request.
   * Returns a JSON-RPC response (never throws).
   */
  async processRequest(request: JsonRpcRequest): Promise<JsonRpcResponse> {
    // Validate JSON-RPC version
    if (request.jsonrpc !== '2.0') {
      return this._error(request.id, -32600, 'Invalid Request: jsonrpc must be "2.0"');
    }

    try {
      const result = await this._dispatch(request.method, request.params ?? {});
      return this._result(request.id, result);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return this._error(request.id, -32603, `Internal error: ${message}`);
    }
  }

  /**
   * Process a batch of requests or a single request.
   */
  async process(
    body: JsonRpcRequest | JsonRpcRequest[],
  ): Promise<JsonRpcResponse | JsonRpcResponse[]> {
    if (Array.isArray(body)) {
      return Promise.all(body.map((r) => this.processRequest(r)));
    }
    return this.processRequest(body);
  }

  // ========================================================================
  // Capabilities
  // ========================================================================

  capabilities(): Record<string, unknown> {
    return {
      tools: this.tools.size > 0 ? { listChanged: false } : undefined,
      resources: this.resources.length > 0 ? { listChanged: false } : undefined,
      prompts: this.prompts.length > 0 ? { listChanged: false } : undefined,
    };
  }

  // ========================================================================
  // Internal dispatch
  // ========================================================================

  private async _dispatch(
    method: string,
    params: Record<string, unknown>,
  ): Promise<unknown> {
    switch (method) {
      case 'initialize':
        return {
          protocolVersion: '2025-06-18',
          capabilities: this.capabilities(),
          serverInfo: { name: 'jarvis', version: '0.1.0' },
        };

      case 'tools/list':
        return {
          tools: [...this.tools.values()].map((t) => t.definition),
        };

      case 'tools/call': {
        const toolName = params['name'] as string;
        const toolArgs = (params['arguments'] as Record<string, unknown>) ?? {};
        const entry = this.tools.get(toolName);
        if (!entry) {
          throw new Error(`Unknown tool: ${toolName}`);
        }
        return entry.handler(toolArgs);
      }

      case 'resources/list':
        return { resources: this.resources };

      case 'resources/read': {
        const uri = params['uri'] as string;
        const resource = this.resources.find((r) => r.uri === uri);
        if (!resource) {
          throw new Error(`Unknown resource: ${uri}`);
        }
        return {
          contents: [
            {
              uri: resource.uri,
              mimeType: resource.mimeType,
              text: `Resource: ${resource.name}`,
            },
          ],
        };
      }

      case 'prompts/list':
        return { prompts: this.prompts };

      case 'prompts/get': {
        const promptName = params['name'] as string;
        const handler = this.promptHandlers.get(promptName);
        if (!handler) {
          throw new Error(`Unknown prompt: ${promptName}`);
        }
        return handler(params['arguments'] as Record<string, unknown> | undefined);
      }

      default:
        throw new Error(`Method not found: ${method}`);
    }
  }

  // ========================================================================
  // Response builders
  // ========================================================================

  private _result(id: string | number, result: unknown): JsonRpcResponse {
    return { jsonrpc: '2.0', id, result };
  }

  private _error(
    id: string | number,
    code: number,
    message: string,
  ): JsonRpcResponse {
    return { jsonrpc: '2.0', id, error: { code, message } };
  }
}
