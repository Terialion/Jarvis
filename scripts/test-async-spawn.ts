#!/usr/bin/env node
// ============================================================================
// E2E: Full async spawn test — Supervisor uses Agent tool asynchronously
// ============================================================================
// Usage: npx tsx scripts/test-async-spawn.ts

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

function loadEnvFile(filePath: string): void {
  try {
    const raw = readFileSync(filePath, 'utf-8');
    for (const line of raw.replace(/\r/g, '').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx === -1) continue;
      const key = trimmed.slice(0, eqIdx).trim();
      const value = trimmed.slice(eqIdx + 1).trim();
      if (key && !(key in process.env)) process.env[key] = value;
    }
  } catch { /* ok */ }
}
let dir = process.cwd();
for (let i = 0; i < 5; i++) {
  loadEnvFile(join(dir, '.env'));
  const parent = dir.replace(/[/\\][^/\\]+$/, '');
  if (parent === dir) break;
  dir = parent;
}

import { AgentLoop, AgentMailbox, LLMProvider } from '@jarvis/agent';
import { ToolRegistry, allBuiltinTools, createAgentTool } from '@jarvis/tools';
import { SubagentPool, AgentRegistry, buildSubagentSystemPrompt, toolWhitelistForType, type SubagentConfig } from '@jarvis/subagents';
import { createTalkToTool, createReportTool, createListAgentsTool } from '../packages/subagents/src/tools/index.js';
import type { TalkToDeps, ReportDeps, ListAgentsDeps } from '../packages/subagents/src/tools/index.js';

const model = process.env['JARVIS_LLM_MODEL'] ?? 'deepseek-chat';
const apiKey = process.env['JARVIS_LLM_API_KEY'] ?? process.env['OPENAI_API_KEY'];
const baseURL = process.env['JARVIS_LLM_BASE_URL'] ?? '';

console.log(`[async-test] Model: ${model}\n`);

// ============================================================================
const pool = new SubagentPool(4);
const registry = new AgentRegistry();
const parentMailbox = new AgentMailbox();
pool.setParentMailbox(parentMailbox);

registry.register({
  agentId: 'supervisor', role: 'supervisor', parentId: null, depth: 0,
  agentType: 'general', capabilities: [],
  registeredAt: Date.now(),
});

// ============================================================================
// Pool runner
// ============================================================================
pool.setRunner(async (config: SubagentConfig, mailbox: AgentMailbox) => {
  const subTools = new ToolRegistry();
  const whitelist = toolWhitelistForType(config.agentType);
  for (const tool of allBuiltinTools) {
    if (!whitelist || whitelist.includes(tool.name)) subTools.register(tool);
  }

  registry.register({
    agentId: config.agentId, role: config.agentType,
    parentId: 'supervisor', depth: config.depth ?? 1,
    agentType: config.agentType, capabilities: [],
    registeredAt: Date.now(),
  });

  const provider = new LLMProvider({ model, apiKey, baseURL });
  const subLoop = new AgentLoop({
    model: { model, apiKey, baseURL },
    maxTurns: config.budgetSteps ?? 8,
    tools: subTools,
    provider,
    mailbox,
    maxSteps: config.budgetSteps ?? 8,
    systemPrompt: buildSubagentSystemPrompt({
      task: config.task, depth: config.depth ?? 1,
      parentId: 'supervisor', agentType: config.agentType,
    }),
  });

  console.log(`  [sub] ${config.agentId} STARTED`);
  const result = await subLoop.run(config.task);
  console.log(`  [sub] ${config.agentId} DONE (${result.turnsUsed}t)`);
  return {
    agentId: config.agentId,
    status: 'completed' as const,
    answer: result.answer,
    turnsUsed: result.turnsUsed,
  };
});

// ============================================================================
// Supervisor
// ============================================================================
async function main() {
  const supTools = new ToolRegistry();
  for (const tool of allBuiltinTools) supTools.register(tool);
  supTools.register(createAgentTool(pool));
  supTools.register(createListAgentsTool({ registry, selfId: 'supervisor' } as ListAgentsDeps) as any);

  const supProvider = new LLMProvider({ model, apiKey, baseURL });
  const supervisor = new AgentLoop({
    model: { model, apiKey, baseURL },
    maxTurns: 15,
    tools: supTools,
    provider: supProvider,
    mailbox: parentMailbox,
    maxSteps: 12,
  });

  const task = [
    'You are a supervisor. Spawn 2 subagents ASYNCHRONOUSLY:',
    '1. Agent type=explore: "Find all *.ts files in packages/agent/src and count them"',
    '2. Agent type=explore: "Find all class definitions in packages/agent/src and list their names"',
    '',
    'CRITICAL: The Agent tool returns IMMEDIATELY (asynchronous mode). Subagent results',
    'will arrive in your mailbox automatically at the start of the NEXT turn.',
    'After spawning BOTH agents, continue taking actions (e.g., read a file or list_agents)',
    'to advance turns. Each turn, check if results arrived. Once you have BOTH results,',
    'synthesize a final summary.',
    '',
    'DO NOT wait — spawn both, then do small actions to advance turns until results arrive.',
  ].join('\n');

  console.log('[async-test] Running supervisor...\n');
  const result = await supervisor.run(task);

  console.log('\n=== FINAL ANSWER ===');
  console.log(result.answer);
  console.log('\n====================');
  console.log(`[async-test] Turns: ${result.turnsUsed}, Stop: ${result.stopReason}`);

  // Show parent mailbox for verification
  const parentMails = parentMailbox.drain();
  console.log(`[async-test] Parent mailbox remaining: ${parentMails.length}`);
  for (const m of parentMails) {
    console.log(`  From: ${m.senderId} — ${m.message.slice(0, 100)}`);
  }

  const allAgents = registry.listAll();
  console.log(`\n[async-test] Agent Tree (${allAgents.length}):`);
  for (const agent of allAgents) {
    console.log(`  ${'  '.repeat(agent.depth)}${agent.agentId} (${agent.role}, depth=${agent.depth})`);
  }

  pool.shutdown();
}

main().catch((err) => {
  console.error('[async-test] Error:', err instanceof Error ? err.message : String(err));
  pool.shutdown();
  process.exit(1);
});