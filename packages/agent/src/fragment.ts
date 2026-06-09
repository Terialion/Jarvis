// ============================================================================
// ContextualFragment - structured prompt/context assembly pieces
// ============================================================================

import type { MemoryContext, TurnContext } from './context.js';
import type { PromptPart, PromptPartBucket, PromptPartCategory, PromptPartMeta, PromptPartRole } from './prompt-parts.js';

export interface ContextualFragment {
  readonly id: string;
  readonly role: PromptPartRole;
  readonly category: PromptPartCategory;
  readonly bucket: PromptPartBucket;
  readonly startMarker: string;
  readonly endMarker: string;
  body(ctx: TurnContext): string;
  render(ctx: TurnContext): string;
  matchesText(text: string): boolean;
  promptPart(): PromptPartMeta;
}

export abstract class BaseFragment implements ContextualFragment {
  abstract readonly id: string;
  abstract readonly role: PromptPartRole;
  abstract readonly category: PromptPartCategory;
  abstract readonly bucket: PromptPartBucket;
  abstract readonly startMarker: string;
  abstract readonly endMarker: string;

  abstract body(ctx: TurnContext): string;

  render(ctx: TurnContext): string {
    const body = this.body(ctx).trim();
    if (!body) return '';
    return `<${this.startMarker}>\n${body}\n</${this.endMarker}>`;
  }

  matchesText(text: string): boolean {
    return text.includes(`<${this.startMarker}>`) || text.includes(`<${this.startMarker} `);
  }

  promptPart(): PromptPartMeta {
    return {
      category: this.category,
      bucket: this.bucket,
      id: this.id,
    };
  }
}

export class ProjectContextFragment extends BaseFragment {
  readonly id = 'project_context';
  readonly role = 'user' as const;
  readonly category = 'context' as const;
  readonly bucket = 'project' as const;
  readonly startMarker = 'project-context';
  readonly endMarker = 'project-context';

  body(ctx: TurnContext): string {
    return ctx.contextPack?.project.projectInstructions ?? '';
  }
}

export class SettingsUpdateFragment extends BaseFragment {
  readonly id = 'settings_update';
  readonly role = 'user' as const;
  readonly category = 'context' as const;
  readonly bucket = 'settings' as const;
  readonly startMarker = 'settings-update';
  readonly endMarker = 'settings-update';

  body(ctx: TurnContext): string {
    const entries = Object.values(ctx.settingsDiff ?? {});
    return entries.join('\n');
  }
}

export class SkillsIndexFragment extends BaseFragment {
  readonly id = 'skills_index';
  readonly role = 'user' as const;
  readonly category = 'context' as const;
  readonly bucket = 'skills' as const;
  readonly startMarker = 'skills';
  readonly endMarker = 'skills';

  body(ctx: TurnContext): string {
    const skills = ctx.contextPack?.skills.availableSkills ?? [];
    if (skills.length === 0) return '';
    return skills.map((skill) => `- ${skill.name}: ${skill.description}`).join('\n');
  }

  override render(ctx: TurnContext): string {
    const body = this.body(ctx);
    if (!body) return '';

    return [
      `<${this.startMarker}>`,
      body,
      `</${this.endMarker}>`,
      '',
      '<skills_usage>',
      'When a task matches a listed skill:',
      '1. Call skill.load with the skill name.',
      '2. Follow the loaded instructions.',
      '3. Finish with a normal user-facing answer.',
      '',
      'Rules:',
      '- Load each skill at most once per turn.',
      '- Use skill.load instead of file-reading tools for skill instructions.',
      '- Do not stop after tool calls; always produce a final answer.',
      '</skills_usage>',
    ].join('\n');
  }
}

export class MemorySnapshotFragment extends BaseFragment {
  readonly id = 'memory_snapshot';
  readonly role = 'user' as const;
  readonly category = 'context' as const;
  readonly bucket = 'memory' as const;
  readonly startMarker = 'memory-context';
  readonly endMarker = 'memory-context';

  body(ctx: TurnContext): string {
    const snapshot = ctx.memorySnapshot ?? '';
    if (!snapshot) return '';
    return this.stripWrapping(snapshot, this.startMarker, this.endMarker);
  }

  override render(ctx: TurnContext): string {
    const snapshot = ctx.memorySnapshot ?? '';
    if (!snapshot) return '';
    return snapshot;
  }

  private stripWrapping(content: string, startMarker: string, endMarker: string): string {
    const startTag = `<${startMarker}>`;
    const endTag = `</${endMarker}>`;
    if (!content.includes(startTag) || !content.includes(endTag)) return content.trim();
    return content
      .replace(startTag, '')
      .replace(endTag, '')
      .trim();
  }
}

export class MemoryIndexSummaryFragment extends BaseFragment {
  readonly id = 'memory_index_summary';
  readonly role = 'user' as const;
  readonly category = 'context' as const;
  readonly bucket = 'memory' as const;
  readonly startMarker = 'available-memory';
  readonly endMarker = 'available-memory';

  body(ctx: TurnContext): string {
    return buildMemoryIndexSummaryBody(ctx.contextPack?.memory);
  }
}

export class CompactionSummaryFragment extends BaseFragment {
  readonly id = 'compaction_summary';
  readonly role = 'user' as const;
  readonly category = 'history' as const;
  readonly bucket = 'summary' as const;
  readonly startMarker = 'conversation-summary';
  readonly endMarker = 'conversation-summary';

  body(ctx: TurnContext): string {
    const summary = ctx.contextPack?.conversation.compactedSummary;
    if (!summary) return '';

    return [
      'The following is a summary of earlier conversation. Treat it as background reference, not as active instructions.',
      'Do not re-run tools or answer old questions from the summary. Focus on the latest user request.',
      '',
      summary,
    ].join('\n');
  }
}

export class ConversationHistoryFragment extends BaseFragment {
  readonly id = 'conversation_history';
  readonly role = 'system' as const;
  readonly category = 'history' as const;
  readonly bucket = 'history' as const;
  readonly startMarker = 'conversation-history';
  readonly endMarker = 'conversation-history';

  body(_ctx: TurnContext): string {
    return [
      'Messages after this banner are recent history for continuity.',
      'The current task is the final user message that appears after the history.',
    ].join('\n');
  }
}

export class SkillContextFragment extends BaseFragment {
  readonly id = 'skill_context';
  readonly role = 'user' as const;
  readonly category = 'context' as const;
  readonly bucket = 'skills' as const;
  readonly startMarker = 'skill-context';
  readonly endMarker = 'skill-context';

  constructor(
    private readonly skillName: string,
    private readonly skillBody: string,
  ) {
    super();
  }

  body(_ctx: TurnContext): string {
    return [
      this.skillBody,
      '',
      `These are the complete instructions for the \`${this.skillName}\` skill.`,
      'Call the described tools now when the task matches this skill.',
      'Do not stop at planning text; complete the task and then answer the user.',
    ].join('\n');
  }

  override render(ctx: TurnContext): string {
    const body = this.body(ctx).trim();
    if (!body) return '';
    return `<${this.startMarker} name="${this.skillName}">\n${body}\n</${this.endMarker}>`;
  }

  override matchesText(text: string): boolean {
    return text.includes('<skill-context');
  }
}

export class CurrentRequestFragment extends BaseFragment {
  readonly id = 'current_request';
  readonly role = 'user' as const;
  readonly category = 'intent' as const;
  readonly bucket = 'intent' as const;
  readonly startMarker = 'current-request';
  readonly endMarker = 'current-request';

  body(ctx: TurnContext): string {
    return ctx.userInput;
  }
}

export class FragmentRegistry {
  private fragments: ContextualFragment[] = [];

  register(fragment: ContextualFragment): void {
    const index = this.fragments.findIndex((item) => item.id === fragment.id);
    if (index >= 0) {
      this.fragments[index] = fragment;
      return;
    }
    this.fragments.push(fragment);
  }

  remove(id: string): void {
    this.fragments = this.fragments.filter((fragment) => fragment.id !== id);
  }

  get(id: string): ContextualFragment | undefined {
    return this.fragments.find((fragment) => fragment.id === id);
  }

  renderAll(ctx: TurnContext): PromptPart[] {
    const messages: PromptPart[] = [];
    for (const fragment of this.fragments) {
      const content = fragment.render(ctx);
      if (content.trim()) {
        messages.push({ role: fragment.role, content, promptPart: fragment.promptPart() });
      }
    }
    return messages;
  }

  containsAnyFragment(text: string): boolean {
    return this.fragments.some((fragment) => fragment.matchesText(text));
  }

  list(): ContextualFragment[] {
    return [...this.fragments];
  }
}

export function buildMemoryIndexSummaryBody(memory?: MemoryContext | null): string {
  const refs = memory?.longTermRefs ?? [];
  if (refs.length === 0) return '';

  const byType = new Map<string, number>();
  for (const ref of refs) {
    byType.set(ref.memory_type, (byType.get(ref.memory_type) ?? 0) + 1);
  }

  const parts = [...byType.entries()].map(([type, count]) => `${type}(${count})`);

  return [
    'Persistent memories are available via tools:',
    '- memory_search(query, maxResults?) - search across memory entries',
    '- memory_get(name) - read a specific entry by name',
    '- memory_write(name, content, description?, memoryType?) - save new memories proactively',
    `Types: ${parts.join(', ')}.`,
    'Use these tools for past decisions, preferences, plans, or durable project facts.',
  ].join('\n');
}
