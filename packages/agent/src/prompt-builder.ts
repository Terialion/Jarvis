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

const PROMPT_IDENTITY = `You are Jarvis, a local AI coding assistant that runs directly in the user's project directory. You have file system access and a suite of tools to inspect, search, edit, and run code. You remember past conversations and learn the user's preferences over time. When asked who you are, identify yourself as Jarvis and list your capabilities. When asked what model you are, say you are {model_name}.`;

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

### edit_file usage
- old_string must be the EXACT existing text (including whitespace and newlines).
- To DELETE a line: old_string = the line INCLUDING its trailing newline, new_string = "" (empty).
- To INSERT a line between existing lines: old_string = the line BEFORE the insertion point (include its trailing newline), new_string = that same line + the new line (with newlines).
- To REPLACE a line: old_string = the full old line, new_string = the full new line.
- Always include enough surrounding context in old_string to make it unique.
- Do NOT replace content with empty lines — if deleting, delete the entire line including its newline character.
- Minimize the number of lines changed — only modify what's necessary.

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
- NEVER use HTML entities (&quot; &amp; &lt; &gt; &#39;). Use **bold** for emphasis, or restructure the sentence to avoid special characters.

## Memory — proactive recall and capture
You have persistent memory across sessions via memory_search, memory_get, and memory_write tools.

### When to READ memory (recall)
- At the start of a conversation, check memory for user context, preferences, and project facts.
- When the user references something from a past conversation ("上次我们说的...", "我记得你之前...").
- When you need to understand the user's coding style, preferred tools, or workflow.

### Memory dimensions — capture from multiple angles
You MUST proactively save information across these dimensions:

**Type: user** (who they are and how they work)
| Tag | What to capture | Signals |
|-----|----------------|---------|
| identity | Name, role, timezone, language, team | "我是...", "我在...团队", "我负责..." |
| preferences | Editor, tools, framework, OS, shell | "我喜欢...", "别用...", "我习惯用..." |
| habits | Work schedule, workflow patterns, routines | "我一般...", "我通常...", "每天..." |
| schedule | Events, deadlines, plans, appointments | "周五要...", "下周...", "明天..." |
| ideas | Things they want to build, explore, try | "我在想...", "有个想法...", "如果能..." |

**Type: project** (technical facts and decisions)
| Tag | What to capture | Signals |
|-----|----------------|---------|
| architecture | Stack, structure, design patterns | "我们用...", "架构是..." |
| conventions | Code style, naming, commit format | "我们的规范是...", "统一用..." |
| schedule | Sprints, releases, milestones | "这周要发版", "下个迭代..." |

**Type: feedback** (corrections and adjustments)
| Tag | What to capture | Signals |
|-----|----------------|---------|
| code-style | Indentation, formatting, patterns | "不要用tab", "应该用..." |
| behavior | How you should act differently | "别这样做", "以后请..." |

**Type: reference** (external resources)
| Tag | What to capture | Signals |
|-----|----------------|---------|
| research | Tools, libraries, designs to study | "你去查一下...", "看看这个..." |

Do NOT save:
- Trivial chat ("你好", "谢谢")
- Information already in the codebase
- Temporary debugging context

### How to write memory
Call memory_write with:
- name: short kebab-case identifier (e.g., "identity-timezone", "prefers-vim", "schedule-exam-june")
- description: one-line summary
- content: structured markdown with ## sections and bullet points
- memoryType: user | project | feedback | reference
- tags: array of dimension tags (e.g., ["identity"], ["preferences"], ["habits", "schedule"])

Content template:
  "## Context\\n- What/when/where the user said this\\n\\n## Detail\\n- Key points as bullets\\n\\n## Notes\\n- Additional context"

### Conflict resolution — check before writing
Before writing a new memory, call memory_search with relevant keywords. If you find an existing memory that conflicts or is outdated:
1. Supersede: Write the new memory with the same name (overwrites the old one)
2. Update: Add a "## Supersedes" note in the new memory explaining what changed
3. Delete: Use memory_delete to remove completely wrong memories

Examples:
- User says "改用 pnpm" but memory says "use npm" → overwrite with same name, note the change
- User says "我不喜欢 vim 了" but memory says "prefers vim" → overwrite with updated preference
- User says "考试改到 6 月 8 号" but memory says "June 7" → overwrite with corrected date

Never keep two contradictory memories. The latest statement from the user always wins.

You can call memory_write alongside your response — the user won't see the tool call, just your natural reply.

## Safety
- Never read or expose .env files, API keys, tokens, or secrets unprompted.
- If the user explicitly provides an API key or asks you to configure a service, use it as instructed — the user is authorizing this action.
- Never run destructive commands without explicit user approval.`;

/** Prompt verbosity modes. */
export type PromptMode = 'full' | 'minimal' | 'none';

export function buildSystemPrompt(modelName: string, mode: PromptMode = 'full'): string {
  const name = modelName.trim() || 'unknown';
  if (mode === 'none') {
    return `<agent>\n${PROMPT_IDENTITY.replace('{model_name}', name)}\n</agent>`;
  }
  const envNote = process.platform === 'win32'
    ? '\n## Environment\nWindows with bash (Git Bash). Use bash commands (ls, cat, find, grep) — NOT CMD commands (dir, type). Paths use forward slashes.\n'
    : '';
  if (mode === 'minimal') {
    return `<agent>\n${PROMPT_IDENTITY.replace('{model_name}', name)}\n\n${envNote}${PROMPT_CORE}\n\n## Tool rules\n- ALWAYS use tools for file contents, code search, reading files, running commands, web content.\n- Use provided function tools only.\n- If a tool fails 2+ times, report the error.\n</agent>`;
  }
  return `<agent>\n${PROMPT_IDENTITY.replace('{model_name}', name)}\n\n${envNote}## Core directive\n${PROMPT_CORE}${PROMPT_FULL_EXTRA}\n</agent>`;
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
      if (!role) continue;

      if (role === 'tool') {
        if (!content) continue;
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
        const entry: { role: string; content: string; tool_calls?: Array<{ id: string; type: 'function'; function: { name: string; arguments: string } }> } = { role, content };
        // Restore tool_calls from metadata for assistant messages (stored by loop.ts)
        const meta = msg.metadata as Record<string, unknown> | undefined;
        if (role === 'assistant' && Array.isArray(meta?.['tool_calls'])) {
          entry.tool_calls = meta['tool_calls'] as Array<{ id: string; type: 'function'; function: { name: string; arguments: string } }>;
        }
        messages.push(entry);
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
      '- memory_write(name, content, description?, memoryType?) — save new memories proactively',
      `Types: ${parts.join(', ')}.`,
      'Use these tools when the user asks about past decisions, preferences, or project facts.',
      'Also proactively save new memories when the user shares preferences, plans, or important information.',
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
