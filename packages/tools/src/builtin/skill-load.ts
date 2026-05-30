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
    const rawSkillName = String(args.name ?? args.skill ?? args.skill_name ?? '').trim();
    if (!rawSkillName) {
      return JSON.stringify({ error: 'Missing required parameter: name' });
    }

    const normalizeSkillName = (value: string): string => {
      const trimmed = value.trim();
      const unquoted = trimmed
        .replace(/^["'`]+/, '')
        .replace(/["'`]+$/, '')
        .trim();
      return unquoted.toLowerCase();
    };

    const directCandidates = [
      rawSkillName,
      rawSkillName.replace(/^["'`]+|["'`]+$/g, '').trim(),
    ].filter(Boolean);

    let skill = directCandidates
      .map((candidate) => supplier.get(candidate))
      .find((candidate) => Boolean(candidate));

    if (!skill) {
      const loadables = supplier.listLoadable();
      const wanted = normalizeSkillName(rawSkillName);
      const match = loadables.find((entry) => normalizeSkillName(entry.name) === wanted);
      if (match) {
        skill = supplier.get(match.name);
      }
    }

    if (!skill) {
      const available = supplier.listLoadable().map((s) => s.name).join(', ');
      return JSON.stringify({
        error: `Skill "${rawSkillName}" not found. Available skills: ${available}`,
      });
    }

    if (!skill.enabled || skill.quarantined) {
      return JSON.stringify({
        error: `Skill "${rawSkillName}" is not loadable (disabled or quarantined).`,
      });
    }

    const body = supplier.loadBody(skill);
    if (!body) {
      return JSON.stringify({
        error: `Skill "${rawSkillName}" found but its SKILL.md body could not be loaded.`,
      });
    }

    return JSON.stringify({
      skill_name: skill.name,
      body,
      metadata: {
        name: skill.name,
        description: skill.description,
        // allowedTools intentionally omitted — the loop reads it from
        // SkillRegistry directly for activeAllowedTools enforcement.
        // Exposing it in the response metadata risks confusing the model.
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

// ============================================================================
// Skill — direct skill invocation (Claude Code parity)
// ============================================================================

export const skillSchema = toOpenAITool({
  name: 'Skill',
  description: 'Execute a skill within the main conversation. When a user invokes a slash command or skill by name, call this tool. The skill body will be loaded and its instructions should be followed step by step.',
  parameters: {
    type: 'object',
    properties: {
      skill: { type: 'string', description: 'The name of a skill to invoke.' },
      args: { type: 'string', description: 'Optional arguments to pass to the skill.' },
    },
    required: ['skill'],
  },
});

export function createSkillHandler(supplier: SkillSupplier): ToolHandler {
  return (args: Record<string, unknown>, _context: ToolContext): string => {
    const skillName = String(args.skill ?? '').trim();
    const skillArgs = typeof args.args === 'string' ? args.args.trim() : undefined;
    if (!skillName) return JSON.stringify({ error: 'Missing required parameter: skill' });
    const skill = supplier.get(skillName);
    if (!skill) {
      const available = supplier.listLoadable().map((s) => s.name).join(', ');
      return JSON.stringify({ error: `Skill "${skillName}" not found. Available skills: ${available}` });
    }
    if (!skill.enabled || skill.quarantined) return JSON.stringify({ error: `Skill "${skillName}" is not available (disabled or quarantined).` });
    const body = supplier.loadBody(skill);
    if (!body) return JSON.stringify({ error: `Skill "${skillName}" found but body could not be loaded.` });
    let instructions = body;
    if (skillArgs) instructions = `**Args:** ${skillArgs}\n\n${body}`;
    // NOTE: allowedTools intentionally omitted — the loop enforces tool
    // restrictions from SkillRegistry directly (via activeAllowedTools).
    // Exposing allowedTools in metadata confuses smaller models that interpret
    // an empty array literally as "no tools available" instead of "no restriction".
    return JSON.stringify({ skill_name: skill.name, body: instructions, metadata: { name: skill.name, description: skill.description } });
  };
}

export function createSkillTool(supplier: SkillSupplier): ToolEntry {
  return {
    name: 'Skill', toolset: 'skill', schema: skillSchema, handler: createSkillHandler(supplier),
    isAsync: false, emoji: '🎯', maxResultSizeChars: 50_000,
  };
}
