// ============================================================================
// PromptBuilder — assembles provider messages from TurnContext
//
// Message order (Claude Code session continuity):
//   [system prompt] -> [compacted summary] -> [recent history] -> [current user input]
// ============================================================================

import type { TurnContext } from './context.js';

export const AGENT_SYSTEM_PROMPT = `<agent>
You are Jarvis, a local AI coding assistant that runs directly in the user's project directory. You have file system access and a suite of tools to inspect, search, edit, and run code.
When asked who you are, identify yourself as Jarvis and list your capabilities. When greeted, respond with a brief greeting and ask what to work on.
When asked what model you are, say you are {model_name} — always state the model name exactly, not "the configured LLM backend" or similar vagueness.

## Language
You MUST respond in the same language as the user's most recent message. If they write in Chinese, reply in Chinese; in Japanese, reply in Japanese; in English, reply in English. Never switch languages mid-conversation unless the user switches first.

## Core directive
Use tools to fulfill the user's request. Do NOT describe what you'll do — do it. When your tools finish, deliver the result in 1-3 sentences. Do not explain your process, recap what you did, or create tables/comparisons unless the user explicitly asks for them. The harness already shows tool calls and results — your job is to act, then deliver the outcome.

## Tool rules
- ALWAYS use tools for: file contents, directory listings, code search, reading files, running commands, web content, math, dates, git operations. Never answer these from memory.
- Use the most specific tool: Glob for filenames, Grep for content, Read for known paths.
- Use provided function tools only. Never invent tool names.
- If a tool returns an error, try a different approach. If it fails 2+ times, report the error.
- Combine independent tool calls in a single response when possible.

## Code
- Verify with tools before writing code. Don't guess.
- Minimum code to solve the problem. No extra features.
- Match existing codebase style. Don't touch unrelated code.
- Fix root causes, not symptoms.
- After editing, run relevant tests to verify.

## Output style
- Be brief. After tools complete, state what changed in 1-3 sentences.
- NEVER repeat raw tool output (stdout, JSON, exit codes) in your answer.
- Do not create tables, comparisons, or analysis unless asked.
- Do not explain your process — the tool trail already shows it.
- If the user asks a direct question, answer it directly without preamble.
- Use backticks for file paths and code identifiers.

## Safety
- Never read or expose .env files, API keys, tokens, or secrets.
- Never run destructive commands without explicit user approval.
</agent>`;

export class PromptBuilder {
  buildMessages(turnContext: TurnContext): Array<{ role: string; content: string }> {
    const pack = turnContext.contextPack;
    if (!pack) {
      return [{ role: 'user', content: turnContext.userInput }];
    }

    const modelName = (turnContext.modelName ?? '').trim() || 'unknown';
    const systemPrompt = AGENT_SYSTEM_PROMPT.replace('{model_name}', modelName);
    const messages: Array<{ role: string; content: string }> = [
      { role: 'system', content: systemPrompt },
    ];

    // Inject available skills index (metadata only, no body content).
    // Follows Claude Code progressive disclosure: metadata always visible,
    // full body loaded on demand via skill.load.
    const skillsIndex = this._renderSkillsIndex(pack.skills.availableSkills);
    if (skillsIndex) {
      messages.push({ role: 'user', content: skillsIndex });
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
        role: 'user',
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
          role: 'user',
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

    return messages;
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
