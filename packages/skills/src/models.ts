// ============================================================================
// Skill models — SkillSpec, matching, and execution types
// ============================================================================

export interface SkillSpec {
  /** Unique skill identifier */
  name: string;
  /** Human-readable description */
  description: string;
  /** File path to the SKILL.md file */
  path: string;
  /** Source scope: builtin, project, user, or plugin */
  source: SkillSource;
  /** Allowed tools (short aliases like "read", "bash") — normalized by loader */
  allowedTools: string[];
  /** Inferred risk level */
  riskLevel: SkillRiskLevel;
  /** Whether the skill is enabled */
  enabled: boolean;
  /** Whether the skill is quarantined (not trusted yet) */
  quarantined: boolean;
  /** Trust level 0-100 */
  trustLevel: number;
  /** Tags for matching */
  tags?: string[];
  /** Capability keywords for matching */
  capabilities?: string[];
  /** Example usage patterns for matching */
  examples?: string[];
  /** When-to-use guidance for matching */
  when_to_use?: string;
  /** Slash command name (without leading /), if this skill registers one */
  slashCommand?: string;
  /** Skill type: unknown, executable, hybrid, or reference */
  skill_type?: string;
  /** Raw file modification time (for cache invalidation) */
  mtimeMs?: number;
}

export type SkillSource = 'builtin' | 'project' | 'user' | 'plugin';

export type SkillRiskLevel =
  | 'read_only'
  | 'write_approval_required'
  | 'command'
  | 'network'
  | 'credentialed';

// ============================================================================
// Matching
// ============================================================================

export interface SkillMatch {
  skill: SkillSpec;
  /** Match score 0-100 */
  score: number;
  /** Why the skill matched (tag match, name match, description match) */
  reason: string;
}

export interface SkillSelectionResult {
  /** Matched skills, sorted by score descending */
  matches: SkillMatch[];
  /** Skills explicitly blocked by policy */
  blocked: SkillSpec[];
}

// ============================================================================
// Execution
// ============================================================================

export interface SkillExecutionContext {
  taskText: string;
  sessionId?: string;
  turnId?: string;
  /** Maximum number of skills to include */
  maxSkills?: number;
  /** Maximum total characters for skill instruction blocks */
  maxChars?: number;
}

export interface SkillExecutionResult {
  /** Skills that were executed/included */
  included: SkillSpec[];
  /** Assembled instruction block for the prompt */
  instructionBlock: string;
}
