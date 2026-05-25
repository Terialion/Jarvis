/**
 * Pure logic helpers for PromptInput — extracted so they can be unit-tested
 * without a terminal or React render environment.
 */

/** Move forward by one vim "word" (skip non-spaces, then skip spaces). */
export function wordFwd(s: string, p: number): number {
  let i = p;
  while (i < s.length && s[i] !== " ") i++;
  while (i < s.length && s[i] === " ") i++;
  return i;
}

/** Move backward by one vim "word" (step back over spaces, then over word chars). */
export function wordBwd(s: string, p: number): number {
  let i = p;
  if (i > 0) i--;
  while (i > 0 && s[i] === " ") i--;
  while (i > 0 && s[i - 1] !== " ") i--;
  return i;
}

/**
 * Return the byte offset of the start of `line` (0-based) within a
 * newline-separated string.  Lines are the result of `value.split('\n')`.
 */
export function lineOffset(lines: string[], line: number): number {
  let pos = 0;
  for (let i = 0; i < line; i++) pos += lines[i]!.length + 1;
  return pos;
}

/**
 * Given an absolute cursor position in a multi-line string, return which
 * line index the cursor sits on.
 */
export function cursorLineIndex(lines: string[], cursor: number): number {
  let pos = 0;
  for (let i = 0; i < lines.length; i++) {
    if (cursor <= pos + lines[i]!.length) return i;
    pos += lines[i]!.length + 1;
  }
  return lines.length - 1;
}

/** Count the number of lines in a string (always >= 1). */
export function lineCount(value: string): number {
  return value.split("\n").length;
}

/**
 * Filter commands with scoring: prefix > substring > description match.
 * Returns sorted results, max 50. Matches CC/Codex-style filtering.
 */
export function filterCommands(
  commands: Array<{ name: string; description: string }>,
  value: string,
): Array<{ name: string; description: string }> {
  if (!value.startsWith("/")) return [];
  const query = value.slice(1).toLowerCase();
  if (!query) return commands.slice(0, 50);

  const scored: Array<{ cmd: { name: string; description: string }; score: number }> = [];

  for (const cmd of commands) {
    const name = cmd.name.toLowerCase();
    const desc = cmd.description.toLowerCase();

    if (name === query) {
      scored.push({ cmd, score: 100 }); // exact match
    } else if (name.startsWith(query)) {
      scored.push({ cmd, score: 80 }); // prefix match
    } else if (name.includes(query)) {
      scored.push({ cmd, score: 50 + name.indexOf(query) * -0.1 }); // substring
    } else if (desc.includes(query)) {
      scored.push({ cmd, score: 20 }); // description match
    }
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, 50).map((s) => s.cmd);
}
