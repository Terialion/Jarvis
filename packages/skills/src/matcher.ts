// ============================================================================
// SkillMatcher — score skills against task text
// ============================================================================

import type { SkillSpec, SkillMatch } from './models.js';

export class SkillMatcher {
  /**
   * Match skills against the given text.
   * Returns scored matches sorted by score descending.
   */
  match(text: string, skills: SkillSpec[]): SkillMatch[] {
    const textLower = text.toLowerCase();
    const textWords = this._tokenize(textLower);

    const matches: SkillMatch[] = [];

    for (const skill of skills) {
      let score = 0;
      const reasons: string[] = [];

      // Tag match (highest weight)
      if (skill.tags) {
        for (const tag of skill.tags) {
          if (textLower.includes(tag)) {
            score += 40;
            reasons.push(`tag:${tag}`);
          }
        }
      }

      // Name match (medium weight)
      const nameWords = this._tokenize(skill.name.toLowerCase());
      const nameMatches = nameWords.filter((w) => textWords.includes(w));
      if (nameMatches.length > 0) {
        score += nameMatches.length * 20;
        reasons.push(`name:${nameMatches.join(',')}`);
      }

      // Description match (lower weight)
      const descWords = this._tokenize(skill.description.toLowerCase());
      const descMatches = descWords.filter((w) => textWords.includes(w));
      if (descMatches.length > 0) {
        score += descMatches.length * 10;
        reasons.push(`desc:${descMatches.join(',')}`);
      }

      if (score > 0) {
        matches.push({
          skill,
          score: Math.min(score, 100),
          reason: reasons.join('; '),
        });
      }
    }

    // Sort by score descending, then by name
    matches.sort((a, b) => b.score - a.score || a.skill.name.localeCompare(b.skill.name));

    return matches;
  }

  // ========================================================================
  // Internal
  // ========================================================================

  private _tokenize(text: string): string[] {
    return text
      .split(/[\s,.;:!?()[\]{}"'/\\|`~@#$%^&*+=<>-]+/)
      .filter((w) => w.length >= 2);
  }
}
