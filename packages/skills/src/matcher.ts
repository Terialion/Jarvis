// ============================================================================
// SkillMatcher — score skills against task text (7 dimensions + Chinese)
// Python ref: src/jarvis/skills/matcher.py
// ============================================================================

import type { SkillSpec, SkillMatch } from './models.js';

// ============================================================================
// Weight multipliers for different match fields
// ============================================================================

const WEIGHTS: Record<string, number> = {
  name: 4.0,
  description: 2.5,
  tags: 2.0,
  capabilities: 2.5,
  examples: 1.5,
  when_to_use: 2.0,
};

// ============================================================================
// Chinese-English keyword mapping for common user intents
// ============================================================================

const INTENT_KEYWORDS: Record<string, string[]> = {
  search: ['search', '搜索', '查找', '查询', '检索', '搜'],
  news: ['news', '新闻', '最新', 'today', '今天', 'recent', '最近', 'current', '当前'],
  summary: ['summar', '总结', '摘要', '概括', '概述', '归纳'],
  code: ['code', '代码', '编程', 'programming', '开发', 'generate'],
  file: ['file', '文件', '管理', 'manag', 'organize'],
  web: ['web', '网页', 'fetch', '抓取'],
  arxiv: ['arxiv', '论文', 'paper', '学术', 'research paper'],
  github: ['github', 'issue', 'pr', 'pull request', 'repo'],
  weather: ['weather', '天气', '气象'],
  pdf: ['pdf', '文档', 'document'],
  newsletter: ['newsletter', '简报', '摘要'],
  browser: ['browser', '浏览器', 'playwright', 'selenium'],
  email: ['email', '邮件', 'qq邮箱', 'gmail'],
  social: ['小红书', 'xiaohongshu', '微博', 'weibo', 'social'],
  ppt: ['ppt', 'pptx', '演示', 'presentation', 'slides'],
  docx: ['docx', 'word', '文档'],
  xlsx: ['xlsx', 'excel', '表格', 'spreadsheet'],
  test: ['test', '测试', '检验'],
  run: ['run', '运行', '执行', 'execute'],
  review: ['review', '审查', '审阅', '检查代码', 'review code'],
  fix: ['fix', '修复', '修理', '改正', 'debug'],
};

const CN_VAGUE_SUFFIXES = ['一下', '一下吧', '吧'];

// ============================================================================
// SkillMatchResult — enhanced match result with ambiguity/auto-selection
// ============================================================================

export interface SkillMatchResult {
  matched: boolean;
  selectedSkill: string | null;
  candidates: SkillMatch[];
  confidence: number;
  reason: string;
  needsClarification: boolean;
}

// ============================================================================
// SkillMatcher
// ============================================================================

export class SkillMatcher {
  private ambiguityThreshold: number;
  private minScore: number;

  constructor(opts?: { ambiguityThreshold?: number; minScore?: number }) {
    this.ambiguityThreshold = opts?.ambiguityThreshold ?? 0.15;
    this.minScore = opts?.minScore ?? 0.25;
  }

  /**
   * Match skills against the given text.
   * Returns scored matches sorted by score descending.
   */
  match(text: string, skills: SkillSpec[]): SkillMatch[] {
    const lowered = text.toLowerCase();
    const activeSkills = skills.filter((s) => s.enabled && !s.quarantined);
    if (activeSkills.length === 0) return [];

    const candidates: SkillMatch[] = [];

    for (const skill of activeSkills) {
      const { score, reasons } = this._score(skill, lowered);
      // Scale to 0-100 range and round
      const scaledScore = Math.round(score * 100);
      if (scaledScore >= this.minScore * 100) {
        candidates.push({
          skill,
          score: Math.min(scaledScore, 100),
          reason: reasons.length > 0 ? reasons.join('; ') : `score=${score.toFixed(2)}`,
        });
      }
    }

    candidates.sort((a, b) => b.score - a.score || a.skill.name.localeCompare(b.skill.name));
    return candidates;
  }

  /**
   * Full match with ambiguity detection, auto-selection, and general chat filtering.
   * Mirrors Python's SkillDescriptionMatcher.match().
   */
  matchWithResult(text: string, skills: SkillSpec[]): SkillMatchResult {
    const strippedInput = text.trim();
    const activeSkills = skills.filter((s) => s.enabled && !s.quarantined);

    if (activeSkills.length === 0) {
      return { matched: false, selectedSkill: null, candidates: [], confidence: 0, reason: 'no_active_skills', needsClarification: false };
    }

    const candidates = this.match(text, activeSkills);

    if (candidates.length === 0) {
      if (SkillMatcher.isGeneralChat(strippedInput)) {
        return { matched: false, selectedSkill: null, candidates: [], confidence: 0, reason: 'general_chat_not_skill_request', needsClarification: false };
      }
      if (strippedInput.length <= 5) {
        return {
          matched: true, candidates: [], confidence: 0,
          reason: `ambiguous_short_input: '${strippedInput}' too vague for any skill`,
          selectedSkill: null, needsClarification: true,
        };
      }
      return { matched: false, selectedSkill: null, candidates: [], confidence: 0, reason: 'no_skill_above_min_score', needsClarification: false };
    }

    // Short/vague inputs (≤3 chars) are inherently ambiguous
    if (strippedInput.length <= 3) {
      const top = candidates[0];
      if (top.score < 90) {
        return {
          matched: true, candidates, confidence: top.score / 100,
          reason: `ambiguous_short_input: '${strippedInput}' too vague`,
          selectedSkill: null, needsClarification: true,
        };
      }
    }

    // Chinese vague suffixes for short inputs
    if (strippedInput.length <= 6) {
      const top = candidates[0];
      if (CN_VAGUE_SUFFIXES.some((s) => strippedInput.endsWith(s)) && top.score < 90) {
        return {
          matched: true, candidates, confidence: top.score / 100,
          reason: `ambiguous_vague_input: '${strippedInput}' ends with vague suffix`,
          selectedSkill: null, needsClarification: true,
        };
      }
    }

    // Ambiguity check: close scores with not-too-high confidence
    const top = candidates[0];
    if (candidates.length >= 2) {
      const second = candidates[1];
      const gap = (top.score - second.score) / 100;
      if (gap <= this.ambiguityThreshold && top.score < 70) {
        return {
          matched: true, candidates, confidence: top.score / 100,
          reason: `ambiguous: ${top.skill.name}(${(top.score / 100).toFixed(2)}) vs ${second.skill.name}(${(second.score / 100).toFixed(2)})`,
          selectedSkill: null, needsClarification: true,
        };
      }
    }

    // Auto-select if top candidate has high confidence
    if (top.score >= 60) {
      return {
        matched: true, selectedSkill: top.skill.name, candidates,
        confidence: top.score / 100, reason: top.reason, needsClarification: false,
      };
    }

    return {
      matched: true, candidates, confidence: top.score / 100,
      reason: `low_confidence_top=${top.skill.name}(${(top.score / 100).toFixed(2)})`,
      selectedSkill: null, needsClarification: false,
    };
  }

  // ========================================================================
  // General chat detection
  // ========================================================================

  /**
   * Check if input is a general chat/greeting/identity/capability question.
   * Public so callers can pre-filter before running the matcher.
   */
  static isGeneralChat(text: string): boolean {
    const low = text.toLowerCase().trim();

    // Greetings
    if (['hi', 'hello', 'hey', 'hey there', 'good morning', 'good afternoon', 'good evening',
      '你好', '你好啊', '哈喽', '在吗', '早上好', '下午好', '晚上好', '中午好', '嗨', '嘿', 'ciallo'].includes(low)) {
      return true;
    }
    // Identity questions
    if (['who are you', 'what are you', '你是谁', '你是什么'].includes(low)) {
      return true;
    }
    // Capability questions
    if (['你能做什么', '你会做什么', '你能干嘛', '你会干嘛', '你能帮我什么', '你能帮我做什么',
      '你可以帮我干嘛', '你会什么', '你能编程吗', '你会写代码吗', '你会编程吗',
      'what can you do', 'what u can do', 'what can u do', 'what are you able to do',
      'what can you help me with', 'capabilities', 'can you code'].some((t) => low.includes(t))) {
      return true;
    }
    // Model/config questions
    if (['什么模型', 'what model', 'which model', '你是什么模型'].some((t) => low.includes(t))) {
      return true;
    }
    // Usage help
    if (['怎么让你改代码', 'how can you modify code', 'how do i ask you to change code'].some((t) => low.includes(t))) {
      return true;
    }
    // Simple thanks/acknowledgments
    if (['thanks', 'thank you', 'ok', 'okay', 'great', '谢谢', '多谢'].includes(low)) {
      return true;
    }
    return false;
  }

  // ========================================================================
  // Internal scoring
  // ========================================================================

  private _score(skill: SkillSpec, loweredText: string): { score: number; reasons: string[] } {
    let total = 0;
    const reasons: string[] = [];
    const textTokens = this._tokenizeSet(loweredText);

    const nameLower = skill.name.toLowerCase();
    const nameTokens = this._tokenizeSet(nameLower);

    // Name match
    const nameOverlap = this._intersect(nameTokens, textTokens);
    if (nameOverlap.length > 0) {
      total += WEIGHTS.name * nameOverlap.length / Math.max(nameTokens.length, 1);
      reasons.push(`name tokens matched: ${nameOverlap.join(',')}`);
    }

    // Direct name mention bonus
    if (loweredText.includes(nameLower)) {
      total += 2.0;
      reasons.push('direct name mention');
    }

    // Description match
    const descLower = skill.description.toLowerCase();
    const descTokens = new Set(descLower.split(/[\s,，、。；;:：()\[\]{}]+/).filter(Boolean));
    const descOverlap = this._intersect([...descTokens], textTokens);
    if (descOverlap.length > 0) {
      const score = WEIGHTS.description * descOverlap.length / Math.max(Math.min(descTokens.size, 20), 1);
      total += score;
      reasons.push(`desc tokens: ${descOverlap.join(',')}`);
    }

    // Tags match
    if (skill.tags) {
      for (const tag of skill.tags) {
        if (loweredText.includes(tag.toLowerCase())) {
          total += WEIGHTS.tags;
          reasons.push(`tag matched: ${tag}`);
          break;
        }
      }
    }

    // Capabilities match
    if (skill.capabilities) {
      for (const cap of skill.capabilities) {
        const capLower = cap.toLowerCase();
        const capTokens = this._tokenizeSet(capLower);
        if (this._intersect([...capTokens], textTokens).length > 0 || loweredText.includes(capLower)) {
          total += WEIGHTS.capabilities;
          reasons.push(`cap matched: ${cap}`);
          break;
        }
      }
    }

    // Examples match
    if (skill.examples) {
      for (const example of skill.examples) {
        if (loweredText.includes(example.toLowerCase())) {
          total += WEIGHTS.examples;
          reasons.push(`example matched: ${example.slice(0, 60)}`);
          break;
        }
      }
    }

    // When-to-use match
    if (skill.when_to_use) {
      const whenLower = skill.when_to_use.toLowerCase();
      const whenTokens = new Set(whenLower.split(/[\s,，、。]+/).filter(Boolean));
      const whenOverlap = this._intersect([...whenTokens], textTokens);
      if (whenOverlap.length > 0) {
        total += WEIGHTS.when_to_use * whenOverlap.length / Math.max(whenTokens.size, 1);
        reasons.push(`when_to_use tokens: ${whenOverlap.join(',')}`);
      }
    }

    // Intent keyword bonus — match against skill name, description, capabilities, and tags
    for (const [intentCat, keywords] of Object.entries(INTENT_KEYWORDS)) {
      for (const kw of keywords) {
        if (!loweredText.includes(kw)) continue;
        let matchedIntent = false;

        if (skill.capabilities) {
          for (const cap of skill.capabilities) {
            if (cap.toLowerCase().includes(intentCat)) {
              total += 0.5;
              reasons.push(`intent ${intentCat} -> cap ${cap}`);
              matchedIntent = true;
              break;
            }
          }
        }
        if (!matchedIntent && skill.tags) {
          for (const tag of skill.tags) {
            if (tag.toLowerCase().includes(intentCat)) {
              total += 0.3;
              reasons.push(`intent ${intentCat} -> tag ${tag}`);
              matchedIntent = true;
              break;
            }
          }
        }
        // Fallback: check if keyword or intent category appears in skill name or description
        if (!matchedIntent) {
          const kwInName = nameLower.includes(kw) || nameLower.includes(intentCat);
          const kwInDesc = descLower.includes(kw) || descLower.includes(intentCat);
          if (kwInName || kwInDesc) {
            total += 0.35;
            reasons.push(`intent ${intentCat} (kw=${kw}) -> name/desc match`);
          }
        }
        break;
      }
    }

    return { score: total, reasons };
  }

  private _tokenizeSet(text: string): string[] {
    return [...new Set(text.split(/[-_\s]+/).filter((w) => w.length >= 2))];
  }

  private _intersect(a: string[], b: string[]): string[] {
    const bSet = new Set(b);
    return a.filter((x) => bSet.has(x));
  }
}
