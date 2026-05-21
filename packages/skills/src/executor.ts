// ============================================================================
// SkillExecutor — assemble skill instruction blocks for prompts
// ============================================================================

import { SkillRegistry } from './registry.js';
import { SkillMatcher } from './matcher.js';
import type {
  SkillSpec,
  SkillMatch,
  SkillExecutionContext,
  SkillExecutionResult,
} from './models.js';

// ============================================================================
// SkillExecutor
// ============================================================================

export class SkillExecutor {
  private registry: SkillRegistry;
  private matcher: SkillMatcher;

  constructor(registry: SkillRegistry) {
    this.registry = registry;
    this.matcher = new SkillMatcher();
  }

  /**
   * Match skills against the task text and assemble an instruction block.
   */
  execute(context: SkillExecutionContext): SkillExecutionResult {
    const maxSkills = context.maxSkills ?? 5;
    const maxChars = context.maxChars ?? 10_000;

    // Get loadable skills
    const skills = this.registry.listLoadable();

    // Match
    const matches = this.matcher.match(context.taskText, skills);

    // Take top N
    const topMatches = matches.slice(0, maxSkills);

    // Assemble instruction block
    const included: SkillSpec[] = [];
    let block = '';
    let charsUsed = 0;

    for (const match of topMatches) {
      const body = this.registry.loadBody(match.skill);
      if (!body) continue;

      const header = `\n## Skill: ${match.skill.name}\n${match.skill.description}\n\n`;
      const entry = header + body + '\n';

      if (charsUsed + entry.length > maxChars) break;

      block += entry;
      charsUsed += entry.length;
      included.push(match.skill);
    }

    return {
      included,
      instructionBlock: block.trim(),
    };
  }

  /**
   * Select skills based on policy filtering, then assemble.
   */
  selectAndExecute(
    context: SkillExecutionContext,
    allowlist?: string[],
    denylist?: string[],
  ): SkillExecutionResult {
    const skills = this.registry.listLoadable();
    let matches = this.matcher.match(context.taskText, skills);

    // Apply filters
    if (allowlist && allowlist.length > 0) {
      matches = matches.filter((m) => allowlist.includes(m.skill.name));
    }
    if (denylist && denylist.length > 0) {
      matches = matches.filter((m) => !denylist.includes(m.skill.name));
    }

    const maxSkills = context.maxSkills ?? 5;
    const maxChars = context.maxChars ?? 10_000;
    const topMatches = matches.slice(0, maxSkills);

    const included: SkillSpec[] = [];
    let block = '';
    let charsUsed = 0;

    for (const match of topMatches) {
      const body = this.registry.loadBody(match.skill);
      if (!body) continue;

      const entry = `\n## Skill: ${match.skill.name}\n${body}\n`;
      if (charsUsed + entry.length > maxChars) break;

      block += entry;
      charsUsed += entry.length;
      included.push(match.skill);
    }

    return {
      included,
      instructionBlock: block.trim(),
    };
  }
}
