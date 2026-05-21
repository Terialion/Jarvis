import { describe, it, expect } from 'vitest';
import { MCPServer } from '../server.js';
import { MCPClient } from '../client.js';
import type { JsonRpcRequest, MCPTransport } from '../models.js';

// ============================================================================
// Fake transport for testing MCPClient
// ============================================================================

function fakeTransport(responses: Array<{ result?: unknown; error?: { code: number; message: string } }>): MCPTransport {
  let callIdx = 0;
  return {
    send: async (req: JsonRpcRequest) => {
      const r = responses[callIdx++] ?? { result: {} };
      return {
        jsonrpc: '2.0' as const,
        id: req.id,
        ...r,
      };
    },
    close: () => {},
  };
}

// ============================================================================
// MCPServer
// ============================================================================

describe('MCPServer', () => {
  let server: MCPServer;

  beforeEach(() => {
    server = new MCPServer();
  });

  // ========================================================================
  // Initialize
  // ========================================================================

  it('responds to initialize', async () => {
    const response = await server.processRequest({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
    });

    expect(response.error).toBeUndefined();
    const result = response.result as Record<string, unknown>;
    expect(result.protocolVersion).toBe('2025-06-18');
    expect(result.serverInfo).toEqual({ name: 'jarvis', version: '0.1.0' });
  });

  // ========================================================================
  // Tools
  // ========================================================================

  it('lists registered tools', async () => {
    server.registerTool(
      { name: 'echo', description: 'Echo input', inputSchema: {} },
      async (args) => ({ content: [{ type: 'text', text: JSON.stringify(args) }] }),
    );

    const response = await server.processRequest({
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/list',
    });

    const result = response.result as Record<string, unknown>;
    expect(result.tools).toHaveLength(1);
    expect((result.tools as Array<Record<string, unknown>>)[0].name).toBe('echo');
  });

  it('calls registered tool', async () => {
    server.registerTool(
      { name: 'add', description: 'Add numbers', inputSchema: {} },
      async (args) => ({
        content: [{ type: 'text', text: String(Number(args['a']) + Number(args['b'])) }],
      }),
    );

    const response = await server.processRequest({
      jsonrpc: '2.0',
      id: 3,
      method: 'tools/call',
      params: { name: 'add', arguments: { a: 1, b: 2 } },
    });

    const result = response.result as Record<string, unknown>;
    expect(result.content).toEqual([{ type: 'text', text: '3' }]);
  });

  it('returns error for unknown tool', async () => {
    const response = await server.processRequest({
      jsonrpc: '2.0',
      id: 4,
      method: 'tools/call',
      params: { name: 'nope' },
    });

    expect(response.error).toBeDefined();
    expect(response.error!.code).toBe(-32603);
  });

  // ========================================================================
  // Resources
  // ========================================================================

  it('lists and reads resources', async () => {
    server.registerResource({ uri: 'jarvis://test', name: 'Test Resource' });

    // List
    const list = await server.processRequest({
      jsonrpc: '2.0',
      id: 5,
      method: 'resources/list',
    });
    expect(
      ((list.result as Record<string, unknown>).resources as Array<unknown>),
    ).toHaveLength(1);

    // Read
    const read = await server.processRequest({
      jsonrpc: '2.0',
      id: 6,
      method: 'resources/read',
      params: { uri: 'jarvis://test' },
    });
    expect(read.error).toBeUndefined();
  });

  it('errors on unknown resource URI', async () => {
    const response = await server.processRequest({
      jsonrpc: '2.0',
      id: 7,
      method: 'resources/read',
      params: { uri: 'unknown://nope' },
    });

    expect(response.error).toBeDefined();
  });

  // ========================================================================
  // Prompts
  // ========================================================================

  it('lists and gets prompts', async () => {
    server.registerPrompt(
      { name: 'greet', description: 'Greeting prompt' },
      async (args) => ({
        messages: [{ role: 'user', content: `Hello ${args?.name ?? 'World'}` }],
      }),
    );

    // List
    const list = await server.processRequest({
      jsonrpc: '2.0',
      id: 8,
      method: 'prompts/list',
    });
    expect(
      ((list.result as Record<string, unknown>).prompts as Array<unknown>),
    ).toHaveLength(1);

    // Get
    const got = await server.processRequest({
      jsonrpc: '2.0',
      id: 9,
      method: 'prompts/get',
      params: { name: 'greet', arguments: { name: 'Claude' } },
    });
    const result = got.result as Record<string, unknown>;
    expect(result.messages).toEqual([{ role: 'user', content: 'Hello Claude' }]);
  });

  // ========================================================================
  // JSON-RPC
  // ========================================================================

  it('rejects non-2.0 jsonrpc version', async () => {
    const response = await server.processRequest({
      jsonrpc: '1.0' as '2.0',
      id: 10,
      method: 'initialize',
    });

    expect(response.error).toBeDefined();
    expect(response.error!.code).toBe(-32600);
  });

  it('returns method not found for unknown methods', async () => {
    const response = await server.processRequest({
      jsonrpc: '2.0',
      id: 11,
      method: 'unknown/method',
    });

    expect(response.error).toBeDefined();
    expect(response.error!.code).toBe(-32603);
  });

  it('processes batch requests', async () => {
    const results = await server.process([
      { jsonrpc: '2.0', id: 1, method: 'initialize' },
      { jsonrpc: '2.0', id: 2, method: 'tools/list' },
    ]);

    expect(Array.isArray(results)).toBe(true);
    expect(results).toHaveLength(2);
  });

  // ========================================================================
  // Capabilities
  // ========================================================================

  it('reports capabilities based on registered items', () => {
    // Empty
    expect(server.capabilities()).toEqual({
      tools: undefined,
      resources: undefined,
      prompts: undefined,
    });

    server.registerTool(
      { name: 't', description: '', inputSchema: {} },
      async () => ({ content: [{ type: 'text', text: '' }] }),
    );
    server.registerResource({ uri: 'a://b', name: 'R' });
    server.registerPrompt({ name: 'p' }, async () => ({ messages: [] }));

    const caps = server.capabilities();
    expect(caps.tools).toBeDefined();
    expect(caps.resources).toBeDefined();
    expect(caps.prompts).toBeDefined();
  });
});

// ============================================================================
// MCPClient
// ============================================================================

describe('MCPClient', () => {
  it('connects and discovers tools', async () => {
    const client = new MCPClient();
    const transport = fakeTransport([
      {
        result: {
          serverInfo: { name: 'test-server', version: '1.0.0' },
          capabilities: {},
        },
      },
      { result: { tools: [{ name: 'tool1', description: 'A tool', inputSchema: {} }] } },
      { result: { resources: [] } },
      { result: { prompts: [] } },
    ]);

    const conn = await client.connect(transport);

    expect(conn.serverInfo.name).toBe('test-server');
    expect(conn.tools).toHaveLength(1);
    expect(conn.tools[0].name).toBe('tool1');
  });

  it('calls a tool on a connected server', async () => {
    const client = new MCPClient();
    const transport = fakeTransport([
      { result: { serverInfo: { name: 's', version: '1' }, capabilities: {} } },
      { result: { tools: [] } },
      { result: { resources: [] } },
      { result: { prompts: [] } },
      { result: { content: [{ type: 'text', text: 'done' }] } },
    ]);

    const conn = await client.connect(transport);
    const result = await client.callTool(conn, 'do-thing', { x: 1 });

    expect(result).toEqual({ content: [{ type: 'text', text: 'done' }] });
  });

  it('throws on tool call error', async () => {
    const client = new MCPClient();
    const transport = fakeTransport([
      { result: { serverInfo: { name: 's', version: '1' }, capabilities: {} } },
      { result: { tools: [] } },
      { result: { resources: [] } },
      { result: { prompts: [] } },
      { error: { code: -32602, message: 'Invalid params' } },
    ]);

    const conn = await client.connect(transport);
    await expect(client.callTool(conn, 'bad', {})).rejects.toThrow('Invalid params');
  });

  it('throws on initialize failure', async () => {
    const client = new MCPClient();
    const transport = fakeTransport([
      { error: { code: -32603, message: 'Server error' } },
    ]);

    await expect(client.connect(transport)).rejects.toThrow('MCP initialize failed');
  });

  it('disconnects and removes connection', async () => {
    const client = new MCPClient();
    const transport = fakeTransport([
      { result: { serverInfo: { name: 's', version: '1' }, capabilities: {} } },
      { result: { tools: [] } },
      { result: { resources: [] } },
      { result: { prompts: [] } },
    ]);

    const conn = await client.connect(transport);
    client.disconnect(conn);

    // Connection's cached data still accessible
    const tools = await client.listTools(conn);
    expect(tools).toEqual([]);
  });
});
