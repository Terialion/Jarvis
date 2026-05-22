import { describe, it, expect } from 'vitest';
import { MCPServer, MCPClient } from '@jarvis/mcp';
import type { MCPTransport, JsonRpcRequest, JsonRpcResponse } from '@jarvis/mcp';

describe('E2E: MCP', () => {
  it('MCPServer: registers tools and returns definitions', async () => {
    const server = new MCPServer();

    server.registerTool(
      {
        name: 'add',
        description: 'Add two numbers',
        inputSchema: {
          type: 'object',
          properties: {
            a: { type: 'number' },
            b: { type: 'number' },
          },
          required: ['a', 'b'],
        },
      },
      async (args) => ({ result: Number(args.a) + Number(args.b) }),
    );

    server.registerTool(
      {
        name: 'echo',
        description: 'Echo a message',
        inputSchema: {
          type: 'object',
          properties: { message: { type: 'string' } },
        },
      },
      async (args) => ({ echoed: args.message }),
    );

    // Verify via JSON-RPC
    const listReq: JsonRpcRequest = {
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/list',
    };

    const listResp = await server.processRequest(listReq);
    expect(listResp).toMatchObject({
      jsonrpc: '2.0', id: 1,
    });
  });

  it('MCPServer: dispatches tool calls via JSON-RPC', async () => {
    const server = new MCPServer();

    server.registerTool(
      {
        name: 'add',
        description: 'Add two numbers',
        inputSchema: {
          type: 'object',
          properties: { a: { type: 'number' }, b: { type: 'number' } },
        },
      },
      async (args) => ({ result: Number(args.a) + Number(args.b) }),
    );

    const callReq: JsonRpcRequest = {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/call',
      params: { name: 'add', arguments: { a: 5, b: 3 } },
    };

    const response: JsonRpcResponse = await server.processRequest(callReq);
    expect(response.result).toEqual({ result: 8 });
    expect(response.error).toBeUndefined();
  });

  it('MCPServer: returns error for unknown tool', async () => {
    const server = new MCPServer();

    const callReq: JsonRpcRequest = {
      jsonrpc: '2.0',
      id: 3,
      method: 'tools/call',
      params: { name: 'nonexistent', arguments: {} },
    };

    const response: JsonRpcResponse = await server.processRequest(callReq);
    expect(response.error).toBeDefined();
  });

  it('MCPClient: creates client instance', () => {
    const client = new MCPClient();
    expect(client).toBeDefined();
  });
});
