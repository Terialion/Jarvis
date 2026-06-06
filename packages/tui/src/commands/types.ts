import type React from 'react';
import type { Message, MessageContent } from '../vendor/ui/MessageList.js';
import type { ChatMessage, SlashResult } from '@jarvis/shared';
import type { AgentLoop, TokenTracker } from '@jarvis/agent';
import type { ToolRegistry, PermissionManager } from '@jarvis/tools';
import type { SkillRegistry } from '@jarvis/skills';
import type { SessionStore } from '@jarvis/store';
import type { MCPClient, McpConnectionStatus, McpServerConfig } from '@jarvis/mcp';

export type LiveContextUsage = {
  contextWindow: number;
  usedTokens: number;
  usagePct: number;
  messageCount: number;
  systemPromptTokens?: number;
  projectContextTokens?: number;
  skillsTokens?: number;
  memoryTokens?: number;
  conversationTokens?: number;
  toolSchemasTokens?: number;
  mcpToolsTokens?: number;
  estimatedTotalTokens?: number;
};

export interface SlashCommandCtx {
  store: SessionStore | null;
  sid: string | null;
  skills?: SkillRegistry | null;
  historyRef: React.MutableRefObject<ChatMessage[]>;
  messages: Message[];
  setMessages: (v: Message[] | ((prev: Message[]) => Message[])) => void;
  setIsLoading: (v: boolean) => void;
  cwd: string;
  modelRef: React.MutableRefObject<string>;
  apiKeyRef: React.MutableRefObject<string | undefined>;
  baseURLRef: React.MutableRefObject<string | undefined>;
  reasoningEffortRef: React.MutableRefObject<string>;
  systemPromptRef: React.MutableRefObject<string | undefined>;
  modifiedFilesRef: React.MutableRefObject<Set<string>>;
  getAgent: () => AgentLoop;
  invalidateAgent: () => void;
  onModelChange?: () => void; // Callback to trigger re-render when model changes
  maxTurns: number;
  outputStyleRef: React.MutableRefObject<string>;
  permissionModeRef: React.MutableRefObject<string>;
  permManagerRef: React.MutableRefObject<PermissionManager | null>;
  mcpClientRef: React.MutableRefObject<MCPClient | null>;
  mcpStatusesRef: React.MutableRefObject<McpConnectionStatus[]>;
  mcpConfiguredRef: React.MutableRefObject<Array<{ id: string; plugin?: string; config: McpServerConfig }>>;
  tokenTrackerRef: React.MutableRefObject<TokenTracker | null>;
  toolsRef: React.MutableRefObject<ToolRegistry | null>;
  liveContextUsageRef: React.MutableRefObject<LiveContextUsage | null>;
}

export interface SlashCommandDef {
  name: string;
  description: string;
  usage?: string;
  handler: (args: string[], ctx: SlashCommandCtx) => SlashResult | Promise<SlashResult>;
}

export type REPLCommandDef = {
  name: string;
  description: string;
  onExecute: (args: string, fullInput: string) => void;
};

export function makeSysMsg(msg: string): Message {
  return {
    id: `cmd_${Date.now()}_${crypto.randomUUID().slice(0, 6)}`,
    role: 'assistant',
    content: [{ type: 'text', text: msg } as MessageContent],
    timestamp: Date.now(),
  };
}
