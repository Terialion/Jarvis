/**
 * Lightweight doc consistency check.
 * Verifies README claims don't drift from source constants.
 * Run: pnpm tsx scripts/check-doc-consistency.ts
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { allBuiltinTools } from '../packages/tools/src/index.js';

const ROOT = join(import.meta.dirname, '..');
const README = readFileSync(join(ROOT, 'README.md'), 'utf-8');

let ok = true;

// 1. Built-in tools: README should mention the current count or not specify a static number
const staticCountMatch = README.match(/(\d+)\+?\s*built-in tools/gi);
if (staticCountMatch) {
  const actual = allBuiltinTools.length;
  for (const m of staticCountMatch) {
    const num = parseInt(m.replace(/\D/g, ''), 10);
    if (num && num !== actual) {
      console.error(`[FAIL] README mentions "${m.trim()}" but allBuiltinTools has ${actual} entries.`);
      ok = false;
    }
  }
}

// 2. Permission modes: verify README lists the same modes as source config
const permSection = README.match(/### Permission modes([\s\S]*?)(?=###|$)/);
if (permSection) {
  const text = permSection[1];
  if (!text.includes('workspace_write')) {
    console.error('[FAIL] README permission modes missing workspace_write.');
    ok = false;
  }
  if (!text.includes('accept_edits')) {
    console.error('[FAIL] README permission modes missing accept_edits.');
    ok = false;
  }
  if (!text.includes('bypass')) {
    console.error('[FAIL] README permission modes missing bypass.');
    ok = false;
  }
} else {
  console.error('[FAIL] README missing "Permission modes" section.');
  ok = false;
}

// 3. Verify README mentions ToolRuntime as primary execution path
if (!README.includes('ToolRuntime')) {
  console.error('[FAIL] README missing ToolRuntime mention.');
  ok = false;
}
if (!README.includes('runTurn')) {
  console.error('[FAIL] README missing runTurn mention.');
  ok = false;
}

if (ok) {
  console.log(`[OK] Doc consistency check passed. ${allBuiltinTools.length} built-in tools, permission modes consistent.`);
} else {
  console.log('[INFO] Fix the issues above to keep README consistent with source code.');
  process.exitCode = 1;
}
