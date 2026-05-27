#!/usr/bin/env node
// ============================================================================
// E2E: Peer-to-peer talk_to test
// ============================================================================
// Usage: npx tsx scripts/test-subagents.ts

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Load .env
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
import { SubagentPool, AgentRegistry, toolWhitelistForType, type SubagentConfig } from '@jarvis/subagents';
import { createTalkToTool, createReportTool, createListAgentsTool } from '../packages/subagents/src/tools/index.js';
import type { TalkToDeps, ReportDeps, ListAgentsDeps } from '../packages/subagents/src/tools/index.js';

const model = process.env['JARVIS_LLM_MODEL'] ?? 'deepseek-chat';
const apiKey = process.env['JARVIS_LLM_API_KEY'] ?? process.env['OPENAI_API_KEY'];
const baseURL = process.env['JARVIS_LLM_BASE_URL'] ?? '';

console.log(`[talk_to-test] Model: ${model}\n`);

// ============================================================================
const pool = new SubagentPool(4);
const registry = new AgentRegistry();
const parentMailbox = new AgentMailbox();
const agentLoops = new Map<string, AgentLoop>();

// Register supervisor
registry.register({
  agentId: 'supervisor', role: 'supervisor', parentId: null, depth: 0,
  agentType: 'general', capabilities: ['spawn_agent', 'talk_to', 'report', 'list_agents'],
  registeredAt: Date.now(),
});

// Pre-register the two workers so they can find each other via registry
const workerAId = 'worker-designer';
const workerBId = 'worker-reviewer';
registry.register({
  agentId: workerAId, role: 'API Designer', parentId: 'supervisor', depth: 1,
  agentType: 'general', capabilities: ['talk_to', 'report', 'list_agents', 'bash', 'file_read', 'file_write'],
  registeredAt: Date.now(),
});
registry.register({
  agentId: workerBId, role: 'API Reviewer', parentId: 'supervisor', depth: 1,
  agentType: 'general', capabilities: ['talk_to', 'report', 'list_agents', 'bash', 'file_read', 'file_write'],
  registeredAt: Date.now(),
});

// ============================================================================
// Pool runner — creates AgentLoop per subagent with mailbox + comm tools
// ============================================================================
pool.setRunner(async (config: SubagentConfig, mailbox: AgentMailbox) => {
  const subTools = new ToolRegistry();
  const whitelist = toolWhitelistForType(config.agentType);
  for (const tool of allBuiltinTools) {
    if (!whitelist || whitelist.includes(tool.name)) subTools.register(tool);
  }

  // Communication tools
  subTools.register(createTalkToTool({ registry, pool, senderId: config.agentId } as TalkToDeps) as any);
  subTools.register(createReportTool({
    registry, senderId: config.agentId,
    getMailbox: (id: string) => pool.getMailbox(id),
  } as ReportDeps) as any);
  subTools.register(createListAgentsTool({ registry, selfId: config.agentId } as ListAgentsDeps) as any);

  const provider = new LLMProvider({ model, apiKey, baseURL });
  const subLoop = new AgentLoop({
    model: { model, apiKey, baseURL },
    maxTurns: config.budgetSteps ?? 10,
    tools: subTools,
    provider,
    mailbox,
    maxSteps: config.budgetSteps ?? 10,
  });
  agentLoops.set(config.agentId, subLoop);

  console.log(`  [sub] ${config.agentId} STARTED`);
  const result = await subLoop.run(config.task);
  console.log(`  [sub] ${config.agentId} DONE (${result.turnsUsed} turns)`);
  return {
    agentId: config.agentId,
    status: 'completed' as const,
    answer: result.answer,
    turnsUsed: result.turnsUsed,
  };
});

// ============================================================================
// Run
// ============================================================================
async function main() {
  console.log('[talk_to-test] Spawning 2 agents that must collaborate...\n');

  const summary = [
`You are ${workerAId}, an API Designer. You task: design REST API for task management.

IMPORTANT: You have access to talk_to, report, and list_agents tools. Messages you send via
talk_to arrive IMMEDIATELY in the other agent's inbox. Messages sent TO you arrive
automatically at the start of each turn — you don't need to wait or poll.

STEPS:
1. Use talk_to targetId="${workerBId}" message="Should task updates use PUT (full replace) or PATCH (partial update)? What are the tradeoffs?"
2. After sending, do other work (e.g., read a file or list agents) to advance your turn
3. In the next turn, you will automatically see ${workerBId}'s reply in your conversation
4. Once you have the reply, synthesize a final answer and describe your decision`,

`You are ${workerBId}, an API Reviewer. ${workerAId} will send you a question via talk_to.

IMPORTANT: Messages from other agents appear automatically at the start of each turn.
You do NOT need to wait or poll. Just make a simple tool call (like glob or list_agents)
to advance the turn.

STEPS:
1. First turn: use a simple tool (e.g., glob to look at any file) to advance the turn
2. Second turn: ${workerAId}'s message will appear in your conversation automatically
3. Use talk_to targetId="${workerAId}" with your analysis of PUT vs PATCH
4. Give a clear recommendation with reasoning (PUT is idempotent but bandwidth-heavy; PATCH is partial/RFC 5789 but can be non-idempotent)`,];

  // Submit both agents concurrently
  const handleA = pool.submit({
    agentId: workerAId, agentType: 'general', task: summary[0], budgetSteps: 8, depth: 1,
  });
  const handleB = pool.submit({
    agentId: workerBId, agentType: 'general', task: summary[1], budgetSteps: 8, depth: 1,
  });

  // Wait for both
  const [resultA, resultB] = await Promise.all([handleA.completion, handleB.completion]);

  console.log('\n=== Worker A (Designer) ===');
  console.log(resultA.answer?.slice(0, 300) ?? '(no answer)');
  console.log('\n=== Worker B (Reviewer) ===');
  console.log(resultB.answer?.slice(0, 300) ?? '(no answer)');

  // Check mailboxes for evidence of talk_to
  const mbA = pool.getMailbox(workerAId);
  const mbB = pool.getMailbox(workerBId);

  console.log('\n=== Communication Evidence ===');
  console.log(`Worker A mailbox had pending: ${mbA?.hasPending() ?? 'N/A'} (drained during run)`);
  console.log(`Worker B mailbox had pending: ${mbB?.hasPending() ?? 'N/A'} (drained during run)`);

  // Check parent mailbox for reports
  const reports = parentMailbox.drain();
  console.log(`Parent mailbox messages after drain: ${reports.length}`);
  for (const r of reports) {
    console.log(`  From: ${r.senderId}, content: ${r.message.slice(0, 120)}`);
  }

  pool.shutdown();
}

main().catch((err) => {
  console.error('[talk_to-test] Error:', err instanceof Error ? err.message : String(err));
  pool.shutdown();
  process.exit(1);
});