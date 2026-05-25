// ============================================================================
// skill.load — load full skill instructions on demand
// Progressive disclosure: metadata always visible, body loaded via this tool.
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler, ToolContext } from '../registry.js';

// Minimal interface to avoid coupling @jarvis/tools to @jarvis/skills
export interface SkillSupplier {
  get(name: string): { name: string; path: string; description: string; enabled: boolean; quarantined: boolean; allowedTools: string[] } | undefined;
  listLoadable(): Array<{ name: string; description: string }>;
  loadBody(skill: { path: string }): string | null;
}

// -- schema --
export const skillLoadSchema = toOpenAITool({
  name: 'skill.load',
  description:
    "Load the full instructions and body of a skill by its name. Call this when a user task matches a skill description from the <skills> index. After loading you MUST follow the skill's instructions step by step to complete the task. Load each skill only ONCE per turn.",
  parameters: {
    type: 'object',
    properties: {
      name: {
        type: 'string',
        description: 'The exact name of the skill to load, as shown in the skills index',
      },
    },
    required: ['name'],
  },
});

// -- factory --
export function createSkillLoadHandler(supplier: SkillSupplier): ToolHandler {
  return (args: Record<string, unknown>, _context: ToolContext): string => {
    const skillName = String(args.name ?? '').trim();
    if (!skillName) {
      return JSON.stringify({ error: 'Missing required parameter: name' });
    }

    const skill = supplier.get(skillName);
    if (!skill) {
      const available = supplier.listLoadable().map((s) => s.name).join(', ');
      return JSON.stringify({
        error: `Skill "${skillName}" not found. Available skills: ${available}`,
      });
    }

    if (!skill.enabled || skill.quarantined) {
      return JSON.stringify({
        error: `Skill "${skillName}" is not loadable (disabled or quarantined).`,
      });
    }

    const body = supplier.loadBody(skill);
    if (!body) {
      return JSON.stringify({
        error: `Skill "${skillName}" found but its SKILL.md body could not be loaded.`,
      });
    }

    return JSON.stringify({
      skill_name: skill.name,
      body,
      metadata: {
        name: skill.name,
        description: skill.description,
        allowedTools: skill.allowedTools,
      },
    });
  };
}

export function createSkillLoadTool(supplier: SkillSupplier): ToolEntry {
  return {
    name: 'skill.load',
    toolset: 'skill',
    schema: skillLoadSchema,
    handler: createSkillLoadHandler(supplier),
    isAsync: false,
    emoji: '📦',
    maxResultSizeChars: 50_000,
  };
}
