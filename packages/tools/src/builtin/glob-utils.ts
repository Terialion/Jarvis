// ============================================================================
// Glob utilities — shared by glob and grep tools
// ============================================================================

import { sep } from 'node:path';

/**
 * Match a relative file path against a simple glob pattern.
 * Supports * and ? wildcards, but NOT ** (recursive).
 * Used by grep for file filtering.
 */
export function matchGlob(filePath: string, pattern: string): boolean {
  const normalizedPath = filePath.replace(/\\/g, '/');
  const normalizedPattern = pattern.replace(/\\/g, '/');

  const pathParts = normalizedPath.split('/');
  const patternParts = normalizedPattern.split('/');

  // Simple case: both have same segment count
  if (pathParts.length === patternParts.length) {
    return patternParts.every((pat, i) => segmentMatch(pathParts[i], pat));
  }

  // Check if filename matches (last segment) regardless of directory depth
  // This handles patterns like "*.ts" matching "src/foo/bar.ts"
  const fileName = pathParts[pathParts.length - 1];
  const patternFile = patternParts[patternParts.length - 1];

  return segmentMatch(fileName, patternFile);
}

function segmentMatch(name: string, pattern: string): boolean {
  if (pattern === '*' || pattern === '**') return true;

  let pi = 0;
  let ni = 0;

  while (pi < pattern.length) {
    const ch = pattern[pi];

    if (ch === '*') {
      // * matches everything until the next literal part or end
      pi++;
      if (pi >= pattern.length) return true;

      // Gather the next literal to match after the *
      let nextLit = '';
      while (pi < pattern.length && pattern[pi] !== '*' && pattern[pi] !== '?') {
        nextLit += pattern[pi];
        pi++;
      }

      if (nextLit) {
        const idx = name.indexOf(nextLit, ni);
        if (idx === -1) return false;
        ni = idx + nextLit.length;
      }
      continue;
    }

    if (ch === '?') {
      if (ni >= name.length) return false;
      pi++;
      ni++;
      continue;
    }

    // Literal character
    if (ni >= name.length || name[ni] !== ch) return false;
    pi++;
    ni++;
  }

  return ni === name.length;
}
