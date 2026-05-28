// ============================================================================
// PromptBuilder — assembles provider messages from TurnContext
//
// Message order (Claude Code session continuity):
//   [system prompt] -> [compacted summary] -> [recent history] -> [current user input]
// ============================================================================

import type { TurnContext } from './context.js';
import { injectCacheBreakpoints } from './cache-strategy.js';

// ============================================================================
// System prompt sections for different verbosity levels (OpenClaw pattern)
// ============================================================================

const PROMPT_IDENTITY = `You are Jarvis, a local AI coding assistant that runs directly in the user's project directory. You have file system access and a suite of tools to inspect, search, edit, and run code. When asked who you are, identify yourself as Jarvis and list your capabilities. When asked what model you are, say you are {model_name}.`;

const PROMPT_CORE = `Use tools to fulfill the user's request. Do NOT describe what you'll do — do it. When your tools finish, deliver the result in 1-3 sentences.`;

const PROMPT_FULL_EXTRA = `
## Language
You MUST respond in the same language as the user's most recent message.

## Tool rules
- ALWAYS use tools for: file contents, directory listings, code search, reading files, running commands, web content, math, dates, git operations.
- Use the most specific tool: Glob for filenames, Grep for content, Read for known paths.
- Use provided function tools only. Never invent tool names.
- If a tool returns an error, try a different approach. If it fails 2+ times, report the error.
- Combine independent tool calls in a single response when possible.

## Code
- Verify with tools before writing code. Don't guess.
- Minimum code to solve the problem. No extra features.
- Match existing codebase style. Don't touch unrelated code.
- Fix root causes, not symptoms.

## Output style
- Be brief. After tools complete, state what changed in 1-3 sentences.
- NEVER repeat raw tool output in your answer.
- Do not create tables, comparisons, or analysis unless asked.
- Use backticks for file paths and code identifiers.
- No emoji in tables, lists, or structured data.

## Safety
- Never read or expose .env files, API keys, tokens, or secrets.
- Never run destructive commands without explicit user approval.`;

/** Prompt verbosity modes. */
export type PromptMode = 'full' | 'minimal' | 'none';

export function buildSystemPrompt(modelName: string, mode: PromptMode = 'full'): string {
  const name = modelName.trim() || 'unknown';
  if (mode === 'none') {
    return `<agent>\n${PROMPT_IDENTITY.replace('{model_name}', name)}\n</agent>`;
  }
  if (mode === 'minimal') {
    return `<agent>\n${PROMPT_IDENTITY.replace('{model_name}', name)}\n\n${PROMPT_CORE}\n\n## Tool rules\n- ALWAYS use tools for file contents, code search, reading files, running commands, web content.\n- Use provided function tools only.\n- If a tool fails 2+ times, report the error.\n</agent>`;
  }
  return `<agent>\n${PROMPT_IDENTITY.replace('{model_name}', name)}\n\n## Core directive\n${PROMPT_CORE}${PROMPT_FULL_EXTRA}\n</agent>`;
}

/** @deprecated Use buildSystemPrompt(modelName, mode) instead. */
export const AGENT_SYSTEM_PROMPT = buildSystemPrompt('unknown', 'full');

export class PromptBuilder {
  buildMessages(turnContext: TurnContext): Array<{ role: string; content: string; tool_call_id?: string }> {
    const pack = turnContext.contextPack;
    if (!pack) {
      return [{ role: 'user', content: turnContext.userInput }];
    }

    const modelName = (turnContext.modelName ?? '').trim() || 'unknown';
    const systemPrompt = buildSystemPrompt(modelName);

    const messages: Array<{ role: string; content: string; tool_call_id?: string }> = [
      { role: 'system', content: systemPrompt },
    ];

    // Context diff: on steady-state (non-first) turns, inject only changed settings
    // instead of re-sending full project context (Codex-style context diffing).
    if (!turnContext.isFirstTurn && turnContext.settingsDiff) {
      const diffEntries = Object.values(turnContext.settingsDiff);
      if (diffEntries.length > 0) {
        messages.push({
          role: 'user',
          content: '<settings-update>\n' + diffEntries.join('\n') + '\n</settings-update>',
        });
      }
    } else {
      // First turn or after compaction: inject full project context
      if (pack.project.projectInstructions) {
        messages.push({
          role: 'user',
          content: '<project-context>\n' + pack.project.projectInstructions + '\n</project-context>',
        });
      }
    }

    // Inject available skills index (metadata only, no body content).
    const skillsIndex = this._renderSkillsIndex(pack.skills.availableSkills);
    if (skillsIndex) {
      messages.push({ role: 'user', content: skillsIndex });
    }

    // Inject frozen memory snapshot (captured once at session start, cache-friendly).
    if (turnContext.memorySnapshot) {
      messages.push({ role: 'user', content: turnContext.memorySnapshot });
    }

    // Inject memory index summary (metadata only — use memory_search/memory_get for full content).
    const memorySummary = this._renderMemoryIndexSummary(pack.memory);
    if (memorySummary) {
      messages.push({ role: 'user', content: memorySummary });
    }

    const conv = pack.conversation;

    // Inject compaction summary from previous turns (Claude Code-style).
    if (conv.compactedSummary) {
      messages.push({
        role: 'user',
        content:
          '<conversation-summary>\n' +
          'The following is a summary of the earlier conversation. ' +
          'This is a handoff from previous context — treat it as ' +
          'background reference, NOT as active instructions. ' +
          'Do NOT re-execute tools or commands mentioned here. ' +
          'Do NOT answer questions from the summary — they were ' +
          'already addressed. Your task is the latest user message ' +
          'at the end of this context.\n\n' +
          `${conv.compactedSummary}\n` +
          '</conversation-summary>',
      });
    }

    // Inject recent conversation history as native-role messages.
    const recent = [...conv.recentMessages].slice(-40);
    if (recent.length > 0) {
      messages.push({
        role: 'system',
        content:
          '<conversation-history>\n' +
          'Messages above this point are from earlier turns in ' +
          'this session. They are provided for continuity so you ' +
          'know what was discussed. The user\'s CURRENT request ' +
          'is the LAST message below.\n' +
          '</conversation-history>',
      });
    }

    for (const msg of recent) {
      const role = (msg.role ?? '').trim();
      const content = String(msg.content ?? '');
      if (!role || !content) continue;

      if (role === 'tool') {
        const toolName =
          ((msg.metadata as Record<string, unknown> | undefined)?.['tool_name'] as string) ??
          (msg.tool_call_id as string) ??
          'unknown';
        messages.push({
          role: 'tool',
          tool_call_id: msg.tool_call_id,
          content: `[Previous tool result — ${toolName}]: ${content.slice(0, 3000)}`,
        });
      } else {
        messages.push({ role, content });
      }
    }

    // Soft turn boundary
    messages.push({
      role: 'user',
      content: `─── current request ───\n${turnContext.userInput}`,
    });

    // Inject cache_control breakpoints at stable-content boundaries.
    // System prompt, project context, skills, memory — all stable within a session.
    // Conversation history and current request come after the last breakpoint.
    const cachedMessages = injectCacheBreakpoints(
      messages as Record<string, unknown>[],
      { provider: turnContext.modelProvider, model: turnContext.modelName },
    ) as Array<{ role: string; content: string; tool_call_id?: string }>;

    return cachedMessages;
  }

  private _renderMemoryIndexSummary(
    memory: import('./context.js').MemoryContext,
  ): string | null {
    const refs = memory.longTermRefs;
    if (refs.length === 0) return null;

    const byType = new Map<string, number>();
    for (const ref of refs) {
      byType.set(ref.memory_type, (byType.get(ref.memory_type) ?? 0) + 1);
    }

    const parts: string[] = [];
    for (const [type, count] of byType) {
      parts.push(`${type}(${count})`);
    }

    return [
      '<available-memory>',
      'Persistent memories are available via tools:',
      '- memory_search(query, maxResults?) — search across all memory entries',
      '- memory_get(name) — read a specific entry by name',
      `Types: ${parts.join(', ')}.`,
      'Use these tools when the user asks about past decisions, preferences, or project facts.',
      '</available-memory>',
    ].join('\n');
  }

  private _renderSkillsIndex(
    availableSkills: Array<{ name: string; description: string }>,
  ): string | null {
    if (availableSkills.length === 0) return null;

    const lines: string[] = ['<skills>'];
    for (const s of availableSkills) {
      lines.push(`- ${s.name}: ${s.description}`);
    }
    lines.push('</skills>');
    lines.push('');
    lines.push('<skills_usage>');
    lines.push('When a user task matches a skill description above:');
    lines.push('1. Call skill.load with the skill name to get full instructions.');
    lines.push('2. Follow those instructions step by step to complete the task.');
    lines.push('3. After completing the steps, synthesize a final answer for the user.');
    lines.push('');
    lines.push('Rules:');
    lines.push('- Load each skill only ONCE per turn. Never reload a skill you already loaded.');
    lines.push('- Use skill.load, NOT Read/Grep/Glob tools, to access skill instructions.');
    lines.push('- You MUST produce a final text answer — do not just run tools and stop.');
    lines.push('</skills_usage>');

    return lines.join('\n');
  }
}
