// ============================================================================
// PromptBuilder - assembles provider messages from TurnContext
//
// Message order:
//   [system prompt] -> [context sections] -> [compacted summary]
//   -> [recent history] -> [current user input]
// ============================================================================

import type { TurnContext } from './context.js';
import { injectCacheBreakpoints } from './cache-strategy.js';
import {
  CompactionSummaryFragment,
  ConversationHistoryFragment,
  CurrentRequestFragment,
  FragmentRegistry,
  MemoryIndexSummaryFragment,
  MemorySnapshotFragment,
  ProjectContextFragment,
  SettingsUpdateFragment,
  SkillsIndexFragment,
} from './fragment.js';
import type { PromptPart, PromptPartMeta } from './prompt-parts.js';
import {
  SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
  buildSystemPrompt,
  buildSystemPromptResult,
  type DynamicPromptContext,
  type PromptMode,
  type SystemPromptBuildResult,
  type SystemPromptSection,
} from './prompt-sections.js';

export {
  SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
  buildSystemPrompt,
  buildSystemPromptResult,
};
export type {
  DynamicPromptContext,
  PromptMode,
  SystemPromptBuildResult,
  SystemPromptSection,
};

export type PromptMessage = {
  role: string;
  content: string;
  tool_call_id?: string;
  tool_calls?: Array<{
    id: string;
    type: 'function';
    function: { name: string; arguments: string };
  }>;
  cache_control?: { type: 'ephemeral' };
  promptPart?: PromptPartMeta;
};

function promptPartToMessage(part: PromptPart): PromptMessage {
  return {
    role: part.role,
    content: part.content,
    tool_call_id: part.tool_call_id,
    tool_calls: part.tool_calls,
    promptPart: part.promptPart,
  };
}

/** @deprecated Use buildSystemPrompt(modelName, mode) instead. */
export const AGENT_SYSTEM_PROMPT = buildSystemPrompt('unknown', 'full');

export class PromptBuilder {
  buildParts(turnContext: TurnContext): PromptPart[] {
    const pack = turnContext.contextPack;
    if (!pack) {
      return [{
        role: 'user',
        content: turnContext.userInput,
        promptPart: { category: 'intent', bucket: 'intent', id: 'current_request' },
      }];
    }

    const modelName = (turnContext.modelName ?? '').trim() || 'unknown';
    const systemPrompt = buildSystemPrompt(modelName, 'full', {
      permissionMode: turnContext.permissionMode,
    });

    const parts: PromptPart[] = [{
      role: 'system',
      content: systemPrompt,
      promptPart: { category: 'instruction', bucket: 'system', id: 'system_prompt' },
    }];

    parts.push(...this._buildContextParts(turnContext));
    parts.push(...this._buildConversationParts(turnContext));
    parts.push(...this._buildIntentParts(turnContext));

    return parts;
  }

  buildMessages(turnContext: TurnContext): PromptMessage[] {
    const messages = this.buildParts(turnContext).map(promptPartToMessage);
    return injectCacheBreakpoints(messages as Record<string, unknown>[], {
      provider: turnContext.modelProvider,
      model: turnContext.modelName,
    }) as PromptMessage[];
  }

  private _buildContextParts(turnContext: TurnContext): PromptPart[] {
    const registry = new FragmentRegistry();
    if (!turnContext.isFirstTurn && turnContext.settingsDiff && Object.keys(turnContext.settingsDiff).length > 0) {
      registry.register(new SettingsUpdateFragment());
    } else {
      registry.register(new ProjectContextFragment());
    }
    registry.register(new SkillsIndexFragment());
    registry.register(new MemorySnapshotFragment());
    registry.register(new MemoryIndexSummaryFragment());
    return registry.renderAll(turnContext);
  }

  private _buildConversationParts(
    turnContext: TurnContext,
  ): PromptPart[] {
    const parts: PromptPart[] = [];
    const conversation = turnContext.contextPack!.conversation;

    if (conversation.compactedSummary) {
      const summaryFragment = new CompactionSummaryFragment();
      const content = summaryFragment.render(turnContext);
      if (content) {
        parts.push({
          role: summaryFragment.role,
          content,
          promptPart: summaryFragment.promptPart(),
        });
      }
    }

    const recent = [...conversation.recentMessages].slice(-40);
    if (recent.length > 0) {
      const historyFragment = new ConversationHistoryFragment();
      parts.push({
        role: historyFragment.role,
        content: historyFragment.render(turnContext),
        promptPart: historyFragment.promptPart(),
      });
    }

    for (const msg of recent) {
      const role = (msg.role ?? '').trim();
      const content = String(msg.content ?? '');
      if (!role) continue;

      if (role === 'tool') {
        if (!content) continue;
        const toolName =
          ((msg.metadata as Record<string, unknown> | undefined)?.tool_name as string) ??
          (msg.tool_call_id as string) ??
          'unknown';
        parts.push({
          role: 'tool',
          tool_call_id: msg.tool_call_id,
          content: `[Previous tool result - ${toolName}]: ${content.slice(0, 3000)}`,
          promptPart: { category: 'history', bucket: 'history', id: `history_tool_${msg.tool_call_id ?? 'unknown'}` },
        });
        continue;
      }

      if (!['user', 'assistant', 'system', 'developer'].includes(role)) {
        continue;
      }
      const typedRole = role as Extract<PromptPart['role'], 'user' | 'assistant' | 'system' | 'developer'>;

      const entry: PromptPart = {
        role: typedRole,
        content,
        promptPart: { category: 'history', bucket: 'history', id: `history_${role}_${parts.length}` },
      };
      const meta = msg.metadata as Record<string, unknown> | undefined;
      if (role === 'assistant' && Array.isArray(meta?.tool_calls)) {
        entry.tool_calls = meta.tool_calls as PromptMessage['tool_calls'];
      }
      parts.push(entry);
    }

    return parts;
  }

  private _buildIntentParts(turnContext: TurnContext): PromptPart[] {
    const fragment = new CurrentRequestFragment();
    return [{
      role: fragment.role,
      content: fragment.render(turnContext),
      promptPart: fragment.promptPart(),
    }];
  }
}
