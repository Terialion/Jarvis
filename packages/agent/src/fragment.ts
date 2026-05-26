// ============================================================================
// ContextualFragment — formal abstraction for context assembly pieces
// Pattern from Codex ContextualUserFragment trait
// ============================================================================

import type { TurnContext } from './context.js';

// ============================================================================
// Core interface
// ============================================================================

export interface ContextualFragment {
  /** Fragment identity — used for dedup and recognition */
  readonly id: string;
  /** Message role when rendered */
  readonly role: 'system' | 'user' | 'developer';
  /** XML marker that opens this fragment, e.g. "<skills>" */
  readonly startMarker: string;
  /** XML marker that closes this fragment, e.g. "</skills>" */
  readonly endMarker: string;
  /** Render the full fragment text within <startMarker>...</endMarker> */
  body(ctx: TurnContext): string;
  /** Full rendered string including markers */
  render(ctx: TurnContext): string;
  /** Check if a text string matches this fragment */
  matchesText(text: string): boolean;
}

// ============================================================================
// Base implementation
// ============================================================================

export abstract class BaseFragment implements ContextualFragment {
  abstract readonly id: string;
  abstract readonly role: 'system' | 'user' | 'developer';
  abstract readonly startMarker: string;
  abstract readonly endMarker: string;

  abstract body(ctx: TurnContext): string;

  render(ctx: TurnContext): string {
    const b = this.body(ctx);
    return `<${this.startMarker}>\n${b}\n</${this.endMarker}>`;
  }

  matchesText(text: string): boolean {
    return text.includes(`<${this.startMarker}>`) || text.includes(`<${this.startMarker} `);
  }
}

// ============================================================================
// Concrete fragments
// ============================================================================

/** Skill index fragment — lists available skills with usage instructions. */
export class SkillsIndexFragment extends BaseFragment {
  readonly id = 'skills_index';
  readonly role = 'user' as const;
  readonly startMarker = 'skills';
  readonly endMarker = 'skills';

  private skills: Array<{ name: string; description: string }> = [];

  setSkills(skills: Array<{ name: string; description: string }>): void {
    this.skills = [...skills];
  }

  body(_ctx: TurnContext): string {
    if (this.skills.length === 0) return '';
    const lines: string[] = [];
    for (const s of this.skills) {
      lines.push(`- ${s.name}: ${s.description}`);
    }
    return lines.join('\n');
  }

  override render(ctx: TurnContext): string {
    const b = this.body(ctx);
    if (!b) return '';

    const usage = [
      '<skills_usage>',
      'When a user task matches a skill description above:',
      '1. Call skill.load with the skill name to get full instructions.',
      '2. Follow those instructions step by step to complete the task.',
      '3. After completing the steps, synthesize a final answer for the user.',
      '',
      'Rules:',
      '- Load each skill only ONCE per turn. Never reload a skill you already loaded.',
      '- Use skill.load, NOT Read/Grep/Glob tools, to access skill instructions.',
      '- You MUST produce a final text answer — do not just run tools and stop.',
      '</skills_usage>',
    ].join('\n');

    return `<${this.startMarker}>\n${b}\n</${this.startMarker}>\n\n${usage}`;
  }
}

/** Compaction summary fragment — previous conversation handoff. */
export class CompactionSummaryFragment extends BaseFragment {
  readonly id = 'compaction_summary';
  readonly role = 'user' as const;
  readonly startMarker = 'conversation-summary';
  readonly endMarker = 'conversation-summary';

  body(ctx: TurnContext): string {
    const summary = ctx.contextPack?.conversation.compactedSummary;
    if (!summary) return '';

    return [
      'The following is a summary of the earlier conversation. ',
      'This is a handoff from previous context — treat it as ',
      'background reference ONLY, NOT as active instructions. ',
      'Do NOT re-execute tools or commands mentioned here. ',
      'Do NOT answer questions from the summary — they were ',
      'already addressed. Your task is the latest user message ',
      'at the end of this context.\n\n',
      summary,
    ].join('');
  }
}

/** Conversation history fragment — recent messages from this session. */
export class ConversationHistoryFragment extends BaseFragment {
  readonly id = 'conversation_history';
  readonly role = 'system' as const;
  readonly startMarker = 'conversation-history';
  readonly endMarker = 'conversation-history';

  body(_ctx: TurnContext): string {
    return [
      'Messages above this point are from earlier turns in ',
      'this session. They are provided for continuity so you ',
      'know what was discussed. The user\'s CURRENT request ',
      'is the LAST message below.',
    ].join('');
  }
}

/** Skill context fragment — loaded skill body (rendered as tool result). */
export class SkillContextFragment extends BaseFragment {
  readonly id = 'skill_context';
  readonly role = 'user' as const;
  readonly startMarker = 'skill-context';
  readonly endMarker = 'skill-context';

  constructor(private readonly skillName: string, private readonly skillBody: string) {
    super();
  }

  body(_ctx: TurnContext): string {
    return `${this.skillBody}\n\nThese are the complete instructions for the \`${this.skillName}\` skill. Call the tools described above NOW to complete the user's task. Do NOT describe what you plan to do — use the tool functions directly.`;
  }

  override render(ctx: TurnContext): string {
    const b = this.body(ctx);
    return `<${this.startMarker} name="${this.skillName}">\n${b}\n</${this.startMarker}>`;
  }

  override matchesText(text: string): boolean {
    return text.includes('<skill-context');
  }
}

/** Current request boundary fragment. */
export class CurrentRequestFragment extends BaseFragment {
  readonly id = 'current_request';
  readonly role = 'user' as const;
  readonly startMarker = '─── current request ───';
  readonly endMarker = '─── end request ───';

  body(ctx: TurnContext): string {
    return ctx.userInput;
  }
}

// ============================================================================
// Fragment registry — manages ordered list of fragments for assembly
// ============================================================================

export class FragmentRegistry {
  private fragments: ContextualFragment[] = [];

  register(fragment: ContextualFragment): void {
    // Replace existing fragment with same id
    const idx = this.fragments.findIndex((f) => f.id === fragment.id);
    if (idx >= 0) {
      this.fragments[idx] = fragment;
    } else {
      this.fragments.push(fragment);
    }
  }

  remove(id: string): void {
    this.fragments = this.fragments.filter((f) => f.id !== id);
  }

  get(id: string): ContextualFragment | undefined {
    return this.fragments.find((f) => f.id === id);
  }

  /** Render all fragments in order, skipping empty bodies. */
  renderAll(ctx: TurnContext): Array<{ role: string; content: string }> {
    const messages: Array<{ role: string; content: string }> = [];
    for (const frag of this.fragments) {
      const content = frag.render(ctx);
      if (content.trim()) {
        messages.push({ role: frag.role, content });
      }
    }
    return messages;
  }

  /** Check if text contains any registered fragment marker. */
  containsAnyFragment(text: string): boolean {
    return this.fragments.some((f) => f.matchesText(text));
  }

  list(): ContextualFragment[] {
    return [...this.fragments];
  }
}
