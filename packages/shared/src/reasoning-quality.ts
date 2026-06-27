const REPLACEMENT_CHAR = /\uFFFD/;
const CONTROL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;

function scriptFamilies(text: string): Set<string> {
  const families = new Set<string>();
  for (const char of text) {
    if (/\p{Script=Latin}/u.test(char)) families.add('latin');
    else if (/\p{Script=Han}/u.test(char)) families.add('han');
    else if (/\p{Script=Hiragana}|\p{Script=Katakana}/u.test(char)) families.add('kana');
    else if (/\p{Script=Hangul}/u.test(char)) families.add('hangul');
    else if (/\p{Script=Cyrillic}/u.test(char)) families.add('cyrillic');
    else if (/\p{Script=Thai}/u.test(char)) families.add('thai');
    else if (/\p{Script=Myanmar}/u.test(char)) families.add('myanmar');
    else if (/\p{Script=Khmer}/u.test(char)) families.add('khmer');
    else if (/\p{Script=Arabic}/u.test(char)) families.add('arabic');
    else if (/\p{Script=Devanagari}/u.test(char)) families.add('devanagari');
  }
  return families;
}

export function isLikelyReadableReasoningText(text: string): boolean {
  const normalized = text.replace(CONTROL_CHARS, '').replace(/\s+/g, ' ').trim();
  if (!normalized) return false;
  if (REPLACEMENT_CHAR.test(normalized)) return false;

  const letters = [...normalized].filter((char) => /\p{L}/u.test(char));
  if (letters.length < 8) return true;

  const families = scriptFamilies(normalized);
  if (normalized.length >= 40 && families.size >= 4) return false;

  return true;
}

export function sanitizeReasoningForDisplay(text: string): string {
  const cleaned = text.replace(CONTROL_CHARS, '').trim();
  return isLikelyReadableReasoningText(cleaned) ? cleaned : '';
}
