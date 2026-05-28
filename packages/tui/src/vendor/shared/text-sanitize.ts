// ============================================================================
// Text sanitization — ported from OpenClaw (tui-LVkXuSWn.js + assistant-visible-text-BoF6Ixue.js)
// Pure string processing. Zero framework deps.
// ============================================================================

// ---- Code region detection (OpenClaw:4-27) ----

interface Region {
  start: number;
  end: number;
}

function findCodeRegions(text: string): Region[] {
  const regions: Region[] = [];
  // Fenced code blocks
  for (const match of text.matchAll(/(^|\n)(```|~~~)[^\n]*\n[\s\S]*?(?:\n\2|$)/g)) {
    const start = (match.index ?? 0) + match[1].length;
    regions.push({ start, end: start + match[0].length - match[1].length });
  }
  // Inline code spans
  for (const match of text.matchAll(/`+[^`]+`+/g)) {
    const start = match.index ?? 0;
    const end = start + match[0].length;
    if (!regions.some((r) => start >= r.start && end <= r.end)) {
      regions.push({ start, end });
    }
  }
  regions.sort((a, b) => a.start - b.start);
  return regions;
}

function isInsideCode(pos: number, regions: Region[]): boolean {
  return regions.some((r) => pos >= r.start && pos < r.end);
}

function overlapsCodeRegion(start: number, end: number, regions: Region[]): boolean {
  return regions.some((r) => start < r.end && end > r.start);
}

// ---- Model special token stripping (OpenClaw:44-71) ----

const MODEL_SPECIAL_TOKEN_RE = /<[|｜][^|｜]*[|｜]>/g;

function shouldInsertSeparator(before: string, after: string): boolean {
  return Boolean(before && after && !/\s/.test(before) && !/\s/.test(after));
}

function stripModelSpecialTokens(text: string): string {
  if (!text) return text;
  MODEL_SPECIAL_TOKEN_RE.lastIndex = 0;
  if (!MODEL_SPECIAL_TOKEN_RE.test(text)) return text;
  MODEL_SPECIAL_TOKEN_RE.lastIndex = 0;
  const codeRegions = findCodeRegions(text);
  let out = '';
  let cursor = 0;
  for (const match of text.matchAll(MODEL_SPECIAL_TOKEN_RE)) {
    const matched = match[0];
    const start = match.index ?? 0;
    const end = start + matched.length;
    out += text.slice(cursor, start);
    if (isInsideCode(start, codeRegions) || overlapsCodeRegion(start, end, codeRegions)) {
      out += matched;
    } else if (shouldInsertSeparator(text[start - 1], text[end])) {
      out += ' ';
    }
    cursor = end;
  }
  out += text.slice(cursor);
  return out;
}

// ---- Reasoning tag stripping (OpenClaw:164-236) ----

const QUICK_TAG_RE = /<\s*\/?\s*(?:(?:antml:)?(?:think(?:ing)?|thought)|antthinking|final)\b/i;
const THINKING_TAG_RE = /<\s*(\/?)\s*(?:(?:antml:)?(?:think(?:ing)?|thought)|antthinking)\b[^<>]*>/gi;

interface StripReasoningOptions {
  mode?: 'strict' | 'preserve';
  trim?: 'none' | 'start' | 'both';
}

function applyTrim(value: string, mode: StripReasoningOptions['trim']): string {
  if (mode === 'none') return value;
  if (mode === 'start') return value.trimStart();
  return value.trim();
}

function hasOrphanReasoningCloseBoundary(params: { before: string; after: string }): boolean {
  return params.before.trim().length > 0 && params.after.trim().length > 0;
}

export function stripReasoningTagsFromText(
  text: string,
  options: StripReasoningOptions = {},
): string {
  if (!text) return text;
  if (!QUICK_TAG_RE.test(text)) return text;
  const mode = options.mode ?? 'strict';
  const trimMode = options.trim ?? 'both';

  let cleaned = text;
  const matches = findFinalTagMatches(cleaned);
  THINKING_TAG_RE.lastIndex = 0;
  const hasThinkingTag = THINKING_TAG_RE.test(cleaned);
  THINKING_TAG_RE.lastIndex = 0;
  if (matches.length === 0 && !hasThinkingTag) return text;

  // Remove <final> tags
  if (matches.length > 0) {
    const preCodeRegions = findCodeRegions(cleaned);
    const finalMatches: { start: number; length: number; inCode: boolean }[] = [];
    for (const match of matches) {
      finalMatches.push({
        start: match.index,
        length: match.text.length,
        inCode: isInsideCode(match.index, preCodeRegions),
      });
    }
    for (let i = finalMatches.length - 1; i >= 0; i--) {
      const m = finalMatches[i];
      if (!m.inCode) cleaned = cleaned.slice(0, m.start) + cleaned.slice(m.start + m.length);
    }
  }

  // Remove <thinking>...</thinking> blocks with depth tracking
  const codeRegions = findCodeRegions(cleaned);
  THINKING_TAG_RE.lastIndex = 0;
  let result = '';
  let lastIndex = 0;
  let thinkingDepth = 0;
  let firstUnclosedContentIndex: number | undefined;

  for (const match of cleaned.matchAll(THINKING_TAG_RE)) {
    const idx = match.index ?? 0;
    const isClose = match[1] === '/';
    if (isInsideCode(idx, codeRegions)) continue;

    if (thinkingDepth === 0) {
      if (isClose) {
        const afterIndex = idx + match[0].length;
        const before = cleaned.slice(lastIndex, idx);
        if (hasOrphanReasoningCloseBoundary({ before, after: cleaned.slice(afterIndex) })) {
          result = '';
        } else {
          result += before;
        }
        lastIndex = afterIndex;
        continue;
      }
      result += cleaned.slice(lastIndex, idx);
      thinkingDepth = 1;
      firstUnclosedContentIndex = idx + match[0].length;
    } else if (isClose) {
      thinkingDepth -= 1;
      if (thinkingDepth === 0) firstUnclosedContentIndex = undefined;
    } else {
      thinkingDepth += 1;
    }
    lastIndex = idx + match[0].length;
  }

  if (thinkingDepth === 0 || mode === 'preserve') result += cleaned.slice(lastIndex);
  const trimmedResult = applyTrim(result, trimMode);
  if (
    mode === 'strict' &&
    thinkingDepth > 0 &&
    !trimmedResult &&
    firstUnclosedContentIndex !== undefined &&
    cleaned.trim()
  ) {
    return applyTrim(cleaned.slice(firstUnclosedContentIndex), trimMode);
  }
  return trimmedResult;
}

// ---- Final tag detection (OpenClaw:73-161) ----

interface FinalTagMatch {
  text: string;
  index: number;
  isClose: boolean;
  isSelfClosing: boolean;
}

function parseFinalTag(tagText: string): FinalTagMatch | null {
  if (!tagText.startsWith('<') || !tagText.endsWith('>')) return null;
  let body = tagText.slice(1, -1).trimStart();
  let isClose = false;
  if (body.startsWith('/')) {
    isClose = true;
    body = body.slice(1).trimStart();
  }
  if (!body.toLowerCase().startsWith('final')) return null;
  const boundary = body[5] ?? '';
  if (boundary && !/\s/.test(boundary) && boundary !== '/') return null;
  let rest = body.slice(5);
  if (isClose) return rest.trim().length === 0 ? { isClose: true, isSelfClosing: false, index: 0, text: tagText } : null;
  const trimmedRest = rest.trimEnd();
  const isSelfClosing = trimmedRest.endsWith('/');
  rest = isSelfClosing ? trimmedRest.slice(0, -1) : rest;
  // Simplified attribute parse — just check for valid attribute syntax
  return { isClose: false, isSelfClosing, index: 0, text: tagText };
}

function findFinalTagMatches(text: string): (Required<Omit<FinalTagMatch, 'index'>> & { index: number; text: string })[] {
  const matches: (Required<Omit<FinalTagMatch, 'index'>> & { index: number; text: string })[] = [];
  const re = /<[^<>]*>/g;
  for (const match of text.matchAll(re)) {
    const parsed = parseFinalTag(match[0]);
    if (!parsed) continue;
    matches.push({
      index: match.index ?? 0,
      text: match[0],
      isClose: parsed.isClose,
      isSelfClosing: parsed.isSelfClosing,
    });
  }
  return matches;
}

// ---- Rendering sanitization (OpenClaw:654-759) ----

const REPLACEMENT_CHAR_RE = /�/g;
const MAX_TOKEN_CHARS = 32;
const LONG_TOKEN_RE = /\S{33,}/g;
const LONG_TOKEN_TEST_RE = /\S{33,}/;
const BINARY_LINE_REPLACEMENT_THRESHOLD = 12;
const URL_PREFIX_RE = /^(https?:\/\/|file:\/\/)/i;
const WINDOWS_DRIVE_RE = /^[a-zA-Z]:[\\/]/;
const FILE_LIKE_RE = /^[a-zA-Z0-9._-]+$/;
const EDGE_PUNCTUATION_RE = /^[`"'([{<]+|[`"')\]}>.,:;!?]+$/g;
const ALPHANUMERIC_RE = /[A-Za-z0-9]/;
const TOKENISH_MIN_LENGTH = 24;
const RTL_SCRIPT_RE = /[֐-ࣿיִ-﷿ﹰ-ﻼ]/;
const BIDI_CONTROL_RE = /[‪-‮⁦-⁩]/;
const RTL_ISOLATE_START = '⁧';
const RTL_ISOLATE_END = '⁩';
const FENCED_CODE_RE = /(```|~~~)[^\n]*\n[\s\S]*?\n\1[^\n]*/g;
const INLINE_CODE_RE = /(`+)(?:(?!\1).)+?\1/g;

function hasControlChars(text: string): boolean {
  for (const char of text) {
    const code = char.charCodeAt(0);
    if ((code <= 31 && code !== 9 && code !== 10 && code !== 13) || (code >= 127 && code <= 159)) return true;
  }
  return false;
}

function stripControlChars(text: string): string {
  if (!hasControlChars(text)) return text;
  let sanitized = '';
  for (const char of text) {
    const code = char.charCodeAt(0);
    if (!(code <= 31 && code !== 9 && code !== 10 && code !== 13) && !(code >= 127 && code <= 159)) {
      sanitized += char;
    }
  }
  return sanitized;
}

function chunkToken(token: string, maxChars: number): string[] {
  if (token.length <= maxChars) return [token];
  const chunks: string[] = [];
  for (let i = 0; i < token.length; i += maxChars) chunks.push(token.slice(i, i + maxChars));
  return chunks;
}

function isCopySensitiveToken(token: string): boolean {
  const candidate = token.replace(EDGE_PUNCTUATION_RE, '') || token;
  if (URL_PREFIX_RE.test(candidate)) return true;
  if (candidate.startsWith('/') || candidate.startsWith('~/') || candidate.startsWith('./') || candidate.startsWith('../')) return true;
  if (WINDOWS_DRIVE_RE.test(candidate) || candidate.startsWith('\\\\')) return true;
  if (candidate.includes('/') || candidate.includes('\\')) return true;
  if (FILE_LIKE_RE.test(candidate) && (candidate.includes('_') || candidate.includes('-') || candidate.includes('.'))) return true;
  if (candidate.length >= TOKENISH_MIN_LENGTH && /[a-z]/i.test(candidate) && /\d/.test(candidate)) return true;
  return false;
}

function normalizeLongTokenForDisplay(token: string): string {
  if (isCopySensitiveToken(token)) return token;
  if (!ALPHANUMERIC_RE.test(token)) return token;
  return chunkToken(token, MAX_TOKEN_CHARS).join(' ');
}

interface PartitionSegment {
  kind: 'prose' | 'code';
  text: string;
}

function partitionByRegex(text: string, re: RegExp): PartitionSegment[] {
  const parts: PartitionSegment[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(re)) {
    const start = match.index ?? 0;
    if (start > lastIndex) parts.push({ kind: 'prose', text: text.slice(lastIndex, start) });
    parts.push({ kind: 'code', text: match[0] });
    lastIndex = start + match[0].length;
  }
  if (lastIndex < text.length) parts.push({ kind: 'prose', text: text.slice(lastIndex) });
  return parts;
}

function transformOutsideCode(text: string, transform: (segment: string) => string): string {
  return partitionByRegex(text, FENCED_CODE_RE)
    .map((seg) => {
      if (seg.kind === 'code') return seg.text;
      return partitionByRegex(seg.text, INLINE_CODE_RE)
        .map((s) => (s.kind === 'code' ? s.text : transform(s.text)))
        .join('');
    })
    .join('');
}

function redactBinaryLikeLine(line: string): string {
  const replacementCount = (line.match(REPLACEMENT_CHAR_RE) || []).length;
  if (replacementCount >= BINARY_LINE_REPLACEMENT_THRESHOLD && replacementCount * 2 >= line.length) {
    return '[binary data omitted]';
  }
  return line;
}

function isolateRtlLine(line: string): string {
  if (!RTL_SCRIPT_RE.test(line) || BIDI_CONTROL_RE.test(line)) return line;
  return `${RTL_ISOLATE_START}${line}${RTL_ISOLATE_END}`;
}

function applyRtlIsolation(text: string): string {
  if (!RTL_SCRIPT_RE.test(text)) return text;
  return text.split('\n').map((line) => isolateRtlLine(line)).join('\n');
}

// Simple ANSI strip (avoids external dependency for this utility)
function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1b\[[0-9;]*m/g, '').replace(/\x1b\]8;.*?\x07/g, '');
}

/**
 * Full render-time text sanitization (OpenClaw:748-759).
 * - Strips ANSI escape codes
 * - Strips control characters (except tab, newline, carriage return)
 * - Redacts binary-like lines (many replacement chars)
 * - Splits long tokens (>32 chars) for readability
 * - Applies RTL isolation for bidirectional text
 * - Code blocks (```fenced``` and `inline`) are protected from splitting
 */
export function sanitizeRenderableText(text: string): string {
  if (!text) return text;
  const hasAnsi = text.includes('\x1B');
  const hasReplacementChars = text.includes('�');
  const hasLongTokens = LONG_TOKEN_TEST_RE.test(text);
  const hasControls = hasControlChars(text);

  if (!hasAnsi && !hasReplacementChars && !hasLongTokens && !hasControls) {
    return applyRtlIsolation(text);
  }

  const withoutAnsi = hasAnsi ? stripAnsi(text) : text;
  const withoutControlChars = hasControls ? stripControlChars(withoutAnsi) : withoutAnsi;
  const redacted = hasReplacementChars
    ? withoutControlChars.split('\n').map(redactBinaryLikeLine).join('\n')
    : withoutControlChars;

  return applyRtlIsolation(
    LONG_TOKEN_TEST_RE.test(redacted)
      ? transformOutsideCode(redacted, (segment) =>
          LONG_TOKEN_TEST_RE.test(segment)
            ? segment.replace(LONG_TOKEN_RE, normalizeLongTokenForDisplay)
            : segment,
        )
      : redacted,
  );
}

/**
 * Combined sanitization — strips model scaffolding, then renderable sanitization.
 * Safe to call on any text before TUI display.
 */
export function sanitizeAssistantVisibleText(text: string): string {
  let cleaned = text;
  cleaned = stripModelSpecialTokens(cleaned);
  cleaned = stripReasoningTagsFromText(cleaned, { mode: 'strict', trim: 'both' });
  cleaned = sanitizeRenderableText(cleaned);
  return cleaned.trim();
}
