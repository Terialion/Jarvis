// ============================================================================
// SkillLoader — parse SKILL.md files with YAML frontmatter
// ============================================================================

import * as fs from 'node:fs';
import * as path from 'node:path';
import type { SkillSpec, SkillSource, SkillRiskLevel } from './models.js';

// ============================================================================
// SkillLoader
// ============================================================================

export class SkillLoader {
  /**
   * Parse a single SKILL.md file into a SkillSpec.
   * Returns null if the file doesn't exist or has no valid frontmatter.
   */
  parseSkillFile(filePath: string, source: SkillSource): SkillSpec | null {
    if (!fs.existsSync(filePath)) return null;

    const raw = fs.readFileSync(filePath, 'utf-8');
    const stat = fs.statSync(filePath);
    const parsed = this._parseFrontmatter(raw);

    if (!parsed.name) return null;

    const allowedTools = normalizeAllowedTools(
      (parsed['allowed_tools'] ?? parsed['allowedTools']) as string | undefined,
    );

    return {
      name: parsed.name,
      description: (parsed['description'] as string) ?? '',
      path: filePath,
      source,
      allowedTools,
      riskLevel: inferRiskLevel(parsed['risk_level'] as string | undefined, allowedTools),
      enabled: parsed['enabled'] !== 'false',
      quarantined: parsed['quarantined'] === 'true',
      trustLevel: typeof parsed['trust_level'] === 'string'
        ? parseInt(parsed['trust_level'], 10) || 50
        : 50,
      tags: this._parseTags(parsed['tags'] as string | undefined),
      slashCommand: ((parsed['slash_command'] ?? '') as string).replace(/^\/+/, '') || undefined,
      mtimeMs: stat.mtimeMs,
    };
  }

  /**
   * Discover SKILL.md files in a directory and its subdirectories (up to 3 levels deep).
   */
  discoverSkills(
    rootDir: string,
    source: SkillSource,
  ): SkillSpec[] {
    const skills: SkillSpec[] = [];
    this._scanDir(rootDir, source, skills, 0);
    return skills;
  }

  // ========================================================================
  // Internal
  // ========================================================================

  private _scanDir(
    dir: string,
    source: SkillSource,
    skills: SkillSpec[],
    depth: number,
  ): void {
    if (depth > 3) return;
    if (!fs.existsSync(dir)) return;

    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const full = path.join(dir, entry.name);

      if (entry.isFile() && entry.name === 'SKILL.md') {
        const spec = this.parseSkillFile(full, source);
        if (spec) skills.push(spec);
      } else if (entry.isDirectory()) {
        this._scanDir(full, source, skills, depth + 1);
      }
    }
  }

  private _parseFrontmatter(
    raw: string,
  ): Record<string, string> {
    // Strip \r to handle CRLF line endings before splitting
    const lines = raw.replace(/\r/g, '').split('\n');
    if (lines[0]?.trim() !== '---') return {};

    const endIdx = lines.findIndex((l, i) => i > 0 && l.trim() === '---');
    if (endIdx === -1) return {};

    const fm: Record<string, string> = {};
    let currentKey = '';

    for (let i = 1; i < endIdx; i++) {
      const line = lines[i];
      const match = line.match(/^(\w[\w\s_-]*?):\s*(.*)$/);
      if (match) {
        currentKey = match[1].trim();
        fm[currentKey] = match[2].trim();
      } else if (currentKey && line.trim()) {
        // Continuation line for multi-line values
        fm[currentKey] += '\n' + line;
      }
    }

    return fm;
  }

  private _parseTags(rawTags: string | undefined): string[] | undefined {
    if (!rawTags) return undefined;
    const tags = rawTags
      .split(/[,;]/)
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);
    return tags.length > 0 ? tags : undefined;
  }
}

// ============================================================================
// Normalization helpers
// ============================================================================

/**
 * Normalize tool name aliases to canonical names.
 * Short aliases: "read" → "file-read", "write" → "file-write", etc.
 */
export function normalizeAllowedTools(
  raw: string | undefined,
): string[] {
  if (!raw) return [];
  const parts = raw.split(/[,;\s]+/).filter(Boolean);

  const aliasMap: Record<string, string> = {
    read: 'read_file',
    write: 'write_file',
    edit: 'edit_file',
    bash: 'bash',
    glob: 'glob',
    grep: 'grep',
    web: 'web_fetch',
    search: 'web_search',
  };

  return [...new Set(parts.map((p) => {
    const key = p.trim().toLowerCase();
    return aliasMap[key] ?? key;
  }))];
}

/**
 * Infer the risk level from a risk_level string or from allowed tools.
 */
export function inferRiskLevel(
  rawRisk: string | undefined,
  allowedTools: string[],
): SkillRiskLevel {
  if (rawRisk) {
    const normalized = rawRisk.toLowerCase().replace(/\s/g, '_');
    const valid = [
      'read_only',
      'write_approval_required',
      'command',
      'network',
      'credentialed',
    ];
    if (valid.includes(normalized)) return normalized as SkillRiskLevel;
  }

  // Infer from allowed tools
  const toolSet = new Set(allowedTools);
  if (toolSet.has('bash') || toolSet.has('shell')) return 'command';
  if (toolSet.has('web_fetch') || toolSet.has('web_search')) return 'network';
  if (toolSet.has('write_file') || toolSet.has('edit_file')) return 'write_approval_required';
  return 'read_only';
}

/**
 * Infer the source format from the source directory.
 */
export function inferSourceType(dir: string): SkillSource {
  const normalized = dir.toLowerCase().replace(/\\/g, '/');
  if (normalized.includes('/builtin/') || normalized.includes('/builtin')) return 'builtin';
  if (normalized.includes('/.jarvis/') || normalized.includes('\\.jarvis\\')) return 'project';
  if (normalized.includes('/plugins/') || normalized.includes('\\plugins\\')) return 'plugin';
  return 'user';
}
