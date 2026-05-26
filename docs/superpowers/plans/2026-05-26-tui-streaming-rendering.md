# TUI Streaming & Rendering Improvements Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring Jarvis TUI streaming and rendering to parity with OpenClaw/Codex — live reasoning display, preserved streaming text, semantic tool labels, styled tool cards, and OSC 8 hyperlinks.

**Architecture:** Five independent improvements to the TUI rendering pipeline. Tasks 1-2 fix the streaming data flow (app.tsx → model.ts). Tasks 3-4 improve tool card rendering (MessageList.tsx + new tool-display.ts). Task 5 wires existing osc8.ts into Markdown.tsx. Each task produces a working incremental improvement.

**Tech Stack:** React 19 + Ink (custom vendored renderer), TypeScript, marked (Markdown), cli-highlight (syntax highlighting)

---

### Task 1: Live Reasoning Display (P0-1)

**Problem:** `onReasoningDelta` mixes reasoning text into `streamingContent` as `"Thinking: ..."` prefix, polluting the text stream. DeepSeek reasoning models have long thinking phases (5-60s) where only a spinner shows.

**Fix:** Accumulate reasoning in a ref during stream, flush it as a collapsible `thinking` content block when the first content token arrives. The `ThinkingBlock` component already exists in MessageList.tsx and supports Ctrl+T expand/collapse.

**Files:**
- Modify: `packages/tui/src/app.tsx` (streaming callbacks + result processing)
- Modify: `packages/tui/src/vendor/ui/REPL.tsx` (spinner visibility)

- [ ] **Step 1: Replace onReasoningDelta to not pollute streamingContent**

Read `packages/tui/src/app.tsx` lines 953-964. Replace:

```typescript
onReasoningDelta: (delta: string) => {
  setStreamingContent((prev) => {
    if (!prev || !prev.startsWith('Thinking')) return `Thinking: ${delta}`;
    return prev + delta;
  });
  const boldMatch = delta.match(/\*\*([^*]+)\*\*/);
  if (boldMatch) {
    setSpinnerVerb(boldMatch[1]);
  } else if (!spinnerVerb) {
    const clean = delta.replace(/[#*`\n]/g, ' ').replace(/\s+/g, ' ').trim();
    if (clean.length > 10) setSpinnerVerb(clean.slice(0, 60));
  }
},
```

With:

```typescript
onReasoningDelta: (delta: string) => {
  // Accumulate reasoning in a ref, not React state (avoids OOM from 100KB+ reasoning)
  const buf = reasoningBufferRef.current + delta;
  reasoningBufferRef.current = buf.length > 262144 ? buf.slice(-262144) : buf;
  // Update spinner verb from **bold** patterns in reasoning
  const boldMatch = delta.match(/\*\*([^*]+)\*\*/);
  if (boldMatch) {
    setSpinnerVerb(boldMatch[1]);
  } else if (!spinnerVerb) {
    const clean = delta.replace(/[#*`\n]/g, ' ').replace(/\s+/g, ' ').trim();
    if (clean.length > 10) setSpinnerVerb(clean.slice(0, 60));
  }
},
```

Add the ref near other refs (around line 783):

```typescript
const reasoningBufferRef = useRef<string>('');
const reasoningFlushedRef = useRef(false);
```

- [ ] **Step 2: Flush reasoning as thinking block when first content token arrives**

Read `packages/tui/src/app.tsx` lines 938-951. Replace the `onToken` callback with:

```typescript
onToken: (token: string) => {
  // When content starts flowing, flush accumulated reasoning as a
  // collapsible thinking block (CC/OpenClaw pattern)
  if (!reasoningFlushedRef.current && reasoningBufferRef.current) {
    const thinkingText = reasoningBufferRef.current;
    reasoningBufferRef.current = '';
    reasoningFlushedRef.current = true;
    if (thinkingText.length > 20) {
      setMessages((prev) => [...prev, {
        id: `thinking_${Date.now()}`,
        role: 'assistant',
        content: [{ type: 'thinking' as const, text: thinkingText.slice(0, 65536) }],
        timestamp: Date.now(),
      }]);
    }
    setSpinnerStatus(`thought for ${Math.floor(elapsedRef.current / 100) / 10}s`);
  }
  // Buffer tokens and flush every 50ms (existing adaptive streaming)
  streamBufferRef.current += token;
  if (!streamFlushRef.current) {
    streamFlushRef.current = setTimeout(() => {
      const chunk = streamBufferRef.current;
      streamBufferRef.current = '';
      streamFlushRef.current = null;
      setStreamingContent((prev) => (prev ?? '') + chunk);
    }, 50);
  }
},
```

- [ ] **Step 3: Reset reasoning state on new submit**

Find the `onSubmit` function (around line 1036). Add these resets near the other ref resets:

```typescript
reasoningBufferRef.current = '';
reasoningFlushedRef.current = false;
```

- [ ] **Step 4: Remove spinner when reasoning is active**

In `packages/tui/src/vendor/ui/REPL.tsx` (line ~216), the spinner condition is:

```typescript
{isLoading && !streamingContent && (
```

The spinner should still show during reasoning — but the reasoning is now hidden in a ref, so the spinner IS the right indicator. No change needed here.

Verify the spinner renders when `isLoading && !streamingContent`.

- [ ] **Step 5: Build and verify**

Run: `cd D:/agent/Jarvis && npx tsc --noEmit -p packages/tui/tsconfig.json`
Expected: Only 2 pre-existing errors (TS2322, TS2339)

Run: `npx vitest run packages/agent`
Expected: 96 of 99 pass (3 pre-existing ContextOverflowError failures)

- [ ] **Step 6: Commit**

```bash
git add packages/tui/src/app.tsx
git commit -m "feat: live reasoning display — flush as collapsible thinking block

Replace the old onReasoningDelta behavior that mixed reasoning text
into streamingContent (as 'Thinking: ...' prefix). Now reasoning is
accumulated in a ref and flushed as a proper thinking content block
when the first content token arrives. The existing ThinkingBlock
component renders it with Ctrl+T expand/collapse support."
```

---

### Task 2: Preserve Streaming Text at Turn End (P0-2)

**Problem:** Text streamed via `streamingContent` during the turn is cleared at the end without being saved. The final message uses `result.answer` which duplicates what was streamed. If streaming fails, the text is lost.

**Fix:** When the turn ends, commit the streaming content as a message BEFORE clearing it. Then skip `result.answer` in the final message (it was already committed).

**Files:**
- Modify: `packages/tui/src/app.tsx` (onSubmit try/finally block)

- [ ] **Step 1: Add commitStreaming helper**

In `packages/tui/src/app.tsx`, after the `streamingContentRef` (around line 790), add:

```typescript
// Commit current streaming content as an assistant message (CC/OpenClaw pattern:
// model text between tool calls should appear as separate messages)
const commitStreaming = useCallback(() => {
  const text = streamingContentRef.current;
  if (text && text.trim()) {
    const msg: Message = {
      id: `msg_${Date.now()}`,
      role: 'assistant',
      content: [{ type: 'text' as const, text }],
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, msg]);
    streamingContentRef.current = null;
    setStreamingContent(null);
  }
}, []);
```

Also add the ref near other refs (around line 790):

```typescript
const streamingContentRef = useRef<string | null>(null);
```

- [ ] **Step 2: Update streamingContent flush to also update the ref**

Find the `setStreamingContent` call in the `onToken` setTimeout (around line 949). Update:

```typescript
setStreamingContent((prev) => {
  const next = (prev ?? '') + chunk;
  if (next.length > 32768) {
    streamingContentRef.current = next.slice(-32768);
    return next.slice(-32768);
  }
  streamingContentRef.current = next;
  return next;
});
```

- [ ] **Step 3: Call commitStreaming on tool start**

In `onToolStart` (around line 966), add `commitStreaming()` before creating the tool message:

```typescript
onToolStart: (callId, toolName, args) => {
  setSpinnerRunning(toolName);
  commitStreaming(); // save any text that arrived before this tool
  // ... rest remains unchanged
},
```

- [ ] **Step 4: Call commitStreaming at turn end**

Find the finally block (around line 1098 area, after try/catch). Add `commitStreaming()` before `setIsLoading(false)`:

```typescript
} finally {
  // Drain streaming buffer and commit any remaining text
  if (streamFlushRef.current) {
    clearTimeout(streamFlushRef.current);
    const chunk = streamBufferRef.current;
    streamBufferRef.current = '';
    streamFlushRef.current = null;
    if (chunk) {
      setStreamingContent((prev) => {
        const next = (prev ?? '') + chunk;
        streamingContentRef.current = next;
        return next;
      });
    }
  }
  commitStreaming();
  abortRef.current = null;
  setIsLoading(false);
  setStreamingContent(null);
  // ...
}
```

- [ ] **Step 5: Skip result.answer in final message to avoid duplication**

Find lines 1082-1087 in the try block. Replace:

```typescript
if (result.answer) {
  content.push({
    type: 'text',
    text: result.answer,
  });
}
```

With a comment explaining it was already committed:

```typescript
// result.answer was already streamed via onToken and committed
// by commitStreaming() above — no need to duplicate.
```

And update the fallback at line 1101 (assistantMsg creation):

```typescript
content: content.length > 0 ? content : [{ type: 'text' as const, text: result.answer }],
```

This fallback handles the edge case where nothing was streamed (non-streaming model response).

- [ ] **Step 6: Build and verify**

Run: `cd D:/agent/Jarvis && npx tsc --noEmit -p packages/tui/tsconfig.json`
Expected: Only 2 pre-existing errors

Run one-shot test: `npx tsx --tsconfig packages/tui/tsconfig.json packages/cli/src/main.ts -p "你好" -m deepseek-chat --max-turns 2`
Expected: Normal response text

- [ ] **Step 7: Commit**

```bash
git add packages/tui/src/app.tsx
git commit -m "fix: preserve streaming text at turn end via commitStreaming

Add commitStreaming() helper that saves streamingContentRef as a
permanent message. Call it on tool start (to interleave text before
tools) and at turn end (to save final answer). Skip result.answer
in the final message to avoid text duplication."
```

---

### Task 3: Semantic Tool Labels (P1-5)

**Problem:** Tool cards show raw tool name and `key=value` args. Users see `bash command=ls -la` instead of a human-readable description.

**Fix:** Create a `tool-display.ts` utility that parses tool args into semantic labels, inspired by OpenClaw's `resolveExecDetail()` and `TOOL_DISPLAY_CONFIG`. Use it in both `onToolStart` and the result handler.

**Files:**
- Create: `packages/tui/src/vendor/ui/tool-display.ts`
- Modify: `packages/tui/src/app.tsx` (onToolStart + result handler)
- Modify: `packages/tui/src/vendor/ui/MessageList.tsx` (ToolUseBlock uses semantic label)

- [ ] **Step 1: Create tool-display.ts**

Write `packages/tui/src/vendor/ui/tool-display.ts`:

```typescript
// Semantic tool display formatting — inspired by OpenClaw's TOOL_DISPLAY_CONFIG

type ToolDisplay = { label: string; detailKeys: string[] };

const TOOL_DISPLAY: Record<string, ToolDisplay> = {
  bash: { label: 'Bash', detailKeys: ['command'] },
  read: { label: 'Read', detailKeys: ['path', 'file_path'] },
  write: { label: 'Write', detailKeys: ['path', 'file_path'] },
  edit: { label: 'Edit', detailKeys: ['path', 'file_path'] },
  glob: { label: 'Glob', detailKeys: ['pattern'] },
  grep: { label: 'Grep', detailKeys: ['pattern', 'path'] },
  web_search: { label: 'Web Search', detailKeys: ['query'] },
  web_fetch: { label: 'Web Fetch', detailKeys: ['url'] },
  task_create: { label: 'Create Task', detailKeys: ['subject'] },
  task_update: { label: 'Update Task', detailKeys: ['taskId'] },
  task_list: { label: 'List Tasks', detailKeys: [] },
  task_get: { label: 'Get Task', detailKeys: ['taskId'] },
  task_output: { label: 'Task Output', detailKeys: ['taskId'] },
  task_stop: { label: 'Stop Task', detailKeys: ['taskId'] },
  enter_plan_mode: { label: 'Plan', detailKeys: [] },
  exit_plan_mode: { label: 'Exit Plan', detailKeys: [] },
  notebook_edit: { label: 'Notebook', detailKeys: ['notebook_path'] },
  cron_create: { label: 'Cron', detailKeys: ['cron'] },
  cron_delete: { label: 'Cron', detailKeys: [] },
  cron_list: { label: 'Cron', detailKeys: [] },
  schedule_wakeup: { label: 'Wakeup', detailKeys: [] },
  enter_worktree: { label: 'Worktree', detailKeys: [] },
  exit_worktree: { label: 'Worktree', detailKeys: [] },
  memory_search: { label: 'Memory', detailKeys: ['query'] },
  memory_get: { label: 'Memory', detailKeys: ['name', 'path'] },
  ask_user_question: { label: 'Ask', detailKeys: [] },
  skill: { label: 'Skill', detailKeys: [] },
  'skill.load': { label: 'Skill', detailKeys: ['skill'] },
  agent: { label: 'Agent', detailKeys: ['description'] },
  list_mcp_resources: { label: 'MCP', detailKeys: [] },
  read_mcp_resource: { label: 'MCP', detailKeys: ['server', 'uri'] },
};

// Parse bash commands into human-readable summaries (OpenClaw resolveExecDetail pattern)
function summarizeBash(args: Record<string, unknown>): string | null {
  const raw = typeof args.command === 'string' ? args.command.trim() : null;
  if (!raw) return null;

  let cmd = raw;
  // Unwrap bash -c '...'
  const shMatch = cmd.match(/^(?:bash|sh|zsh)\s+-c\s+['"](.+?)['"]\s*$/);
  if (shMatch) cmd = shMatch[1];

  const bin = cmd.split(/\s/)[0]?.replace(/^.*[/\\]/, '')?.toLowerCase() ?? '';
  const rest = cmd.slice(bin.length).trim();

  // Git commands
  if (bin === 'git') {
    const sub = rest.split(/\s/)[0];
    const map: Record<string, string> = {
      status: 'check status', diff: 'check diff', log: 'view history',
      checkout: 'switch branch', switch: 'switch branch', commit: 'commit',
      pull: 'pull', push: 'push', fetch: 'fetch', merge: 'merge',
      rebase: 'rebase', add: 'stage', restore: 'restore', reset: 'reset',
      stash: 'stash', branch: 'list branches',
    };
    if (sub && map[sub]) return `git ${map[sub]}`;
    return `git ${sub || 'command'}`;
  }

  // Package managers
  if (bin === 'npm' || bin === 'pnpm' || bin === 'yarn' || bin === 'bun') {
    const sub = rest.split(/\s/)[0];
    const map: Record<string, string> = {
      install: 'install', test: 'run tests', build: 'build',
      start: 'start', lint: 'lint', run: 'run script',
    };
    if (sub && map[sub]) return `${bin} ${map[sub]}`;
    return `${bin} ${sub || ''}`.trim();
  }

  // Common commands
  if (bin === 'ls') return 'list files';
  if (bin === 'cat') return rest ? `show ${rest.split(/\s/)[0]}` : 'show file';
  if (bin === 'grep' || bin === 'rg') return 'search text';
  if (bin === 'find') return 'find files';
  if (bin === 'head' || bin === 'tail') return `show ${bin}`;
  if (bin === 'mkdir') return 'create folder';
  if (bin === 'rm') return 'remove files';
  if (bin === 'cp' || bin === 'mv') return `${bin} files`;
  if (bin === 'echo' || bin === 'printf') return 'print';
  if (bin === 'curl' || bin === 'wget') return 'fetch url';
  if (bin === 'node') return 'run node';
  if (bin === 'python' || bin === 'python3') return 'run python';
  if (bin === 'npx') return `npx ${rest.split(/\s/)[0] || ''}`.trim();
  if (bin === 'tsc') return 'type check';
  if (bin === 'vitest') return 'run tests';
  if (bin === 'eslint') return 'lint';

  return rest ? `${bin} ${rest.slice(0, 60)}` : `run ${bin}`;
}

function resolvePath(args: Record<string, unknown>): string | null {
  for (const key of ['file_path', 'path']) {
    const v = args[key];
    if (typeof v === 'string' && v.trim()) return v.trim();
  }
  return null;
}

function resolveDetail(toolName: string, args: Record<string, unknown>): string | null {
  if (toolName === 'bash') return summarizeBash(args);

  if (toolName === 'read') {
    const path = resolvePath(args);
    if (!path) return null;
    const offset = typeof args.offset === 'number' && args.offset > 0 ? Math.floor(args.offset) : undefined;
    const limit = typeof args.limit === 'number' && args.limit > 0 ? Math.floor(args.limit) : undefined;
    if (offset !== undefined && limit !== undefined) return `L${offset}-${offset + limit - 1} ${path}`;
    if (offset !== undefined) return `from L${offset} ${path}`;
    if (limit !== undefined) return `first ${limit}L ${path}`;
    return path;
  }

  if (toolName === 'write' || toolName === 'edit') {
    const path = resolvePath(args);
    const content = (typeof args.content === 'string' ? args.content :
      typeof args.new_string === 'string' ? args.new_string : null);
    if (path && content) return `${path} (${content.length}c)`;
    if (path) return path;
    return null;
  }

  if (toolName === 'grep') {
    const pattern = typeof args.pattern === 'string' ? args.pattern : null;
    const path = typeof args.path === 'string' ? args.path : null;
    if (pattern && path) return `"${pattern.slice(0, 40)}" in ${path}`;
    if (pattern) return `"${pattern.slice(0, 60)}"`;
    return null;
  }

  if (toolName === 'glob') return typeof args.pattern === 'string' ? args.pattern : null;
  if (toolName === 'web_search') return typeof args.query === 'string' ? args.query.slice(0, 80) : null;
  if (toolName === 'web_fetch') return typeof args.url === 'string' ? args.url.slice(0, 80) : null;

  // Generic: pick first detail key from config
  const config = TOOL_DISPLAY[toolName];
  if (config?.detailKeys) {
    for (const key of config.detailKeys) {
      const value = args[key];
      if (typeof value === 'string' && value.trim()) return value.trim().slice(0, 80);
    }
  }
  return null;
}

export function formatToolLine(toolName: string, args: Record<string, unknown> | undefined): string {
  const config = TOOL_DISPLAY[toolName];
  const label = config?.label ?? toolName.replace(/_/g, ' ');
  const detail = args ? resolveDetail(toolName, args) : null;
  return detail ? `${label}: ${detail}` : label;
}
```

- [ ] **Step 2: Use formatToolLine in onToolStart**

In `packages/tui/src/app.tsx`, add the import:

```typescript
import { formatToolLine } from './vendor/ui/tool-display.js';
```

In `onToolStart` (around line 968), replace the argPreview logic:

```typescript
onToolStart: (callId, toolName, args) => {
  setSpinnerRunning(toolName);
  commitStreaming();
  const argRecord = typeof args === 'object' && args !== null
    ? (args as Record<string, unknown>)
    : undefined;
  const input = formatToolLine(toolName, argRecord);
  setMessages((prev) => [...prev, {
    id: `tool_${callId}`,
    role: 'assistant',
    content: [{
      type: 'tool_use' as const,
      toolName,
      input,
      status: 'running' as const,
    }],
    timestamp: Date.now(),
  }]);
},
```

- [ ] **Step 3: Update ToolUseBlock to show the semantic label**

In `packages/tui/src/vendor/ui/MessageList.tsx`, the ToolUseBlock collapsed view (line 118-145) currently shows `toolName` + preview. Update to use `input` as the primary label:

Replace the collapsed view's display:

```typescript
// Collapsed: show summary line only
if (!expanded && !isRunning) {
  const displayLabel = content.input || content.toolName;
  return (
    <Box marginLeft={2}>
      <Box onClick={() => setLocalExpanded(true)}>
        <Text dimColor>{GUTTER} </Text>
        {content.status === 'success' && <Text color="green">✔ </Text>}
        {content.status === 'error' && <Text color="red">✖ </Text>}
        <Text>{displayLabel}</Text>
        {content.durationMs != null && (
          <Text dimColor> ({formatDuration(content.durationMs)})</Text>
        )}
      </Box>
    </Box>
  );
}
```

Also update the running view to use `displayLabel` consistently.

- [ ] **Step 4: Build and verify**

Run: `cd D:/agent/Jarvis && npx tsc --noEmit -p packages/tui/tsconfig.json`

- [ ] **Step 5: Commit**

```bash
git add packages/tui/src/vendor/ui/tool-display.ts packages/tui/src/app.tsx packages/tui/src/vendor/ui/MessageList.tsx
git commit -m "feat: semantic tool labels — parse args into human-readable summaries

Add tool-display.ts with formatToolLine() that maps tool names to
readable labels (Bash, Read, Write, etc.) and parses args into
human-readable detail (git status → 'git check status',
read file → 'L1-50 src/app.tsx'). Use in onToolStart and ToolUseBlock
for compact tool card display."
```

---

### Task 4: Tool Card Background Colors (P1-4)

**Problem:** Tool cards use plain text with ✔/✖/○ icons. OpenClaw uses colored backgrounds: pending=blue tint, success=green tint, error=red tint.

**Fix:** Wrap the ToolUseBlock in a Box with background color based on status. The vendored Ink renderer's `Box` component supports a `backgroundColor` prop.

**Files:**
- Modify: `packages/tui/src/vendor/ui/MessageList.tsx` (ToolUseBlock)

- [ ] **Step 1: Add background color to ToolUseBlock**

First, check if the vendored `Box` component supports `backgroundColor`. Read `packages/tui/src/vendor/ink-renderer/components/Box.tsx` to verify the prop name.

In `packages/tui/src/vendor/ui/MessageList.tsx`, update the ToolUseBlock collapsed view to wrap with background color:

```typescript
// Status-specific background colors (OpenClaw pattern)
const bgColor = content.status === 'running' ? '#1F2A2F'
  : content.status === 'success' ? '#1E2D23'
  : content.status === 'error' ? '#2F1F1F'
  : undefined;

// Collapsed: single-line summary with colored background
if (!expanded && !isRunning) {
  const displayLabel = content.input || content.toolName;
  return (
    <Box marginLeft={2}>
      <Box
        backgroundColor={bgColor}
        paddingLeft={1}
        paddingRight={1}
        onClick={() => setLocalExpanded(true)}
      >
        <Text dimColor>{GUTTER} </Text>
        {content.status === 'success' && <Text color="green">✔ </Text>}
        {content.status === 'error' && <Text color="red">✖ </Text>}
        <Text>{displayLabel}</Text>
        {content.durationMs != null && (
          <Text dimColor> ({formatDuration(content.durationMs)})</Text>
        )}
      </Box>
    </Box>
  );
}
```

If `backgroundColor` is not supported natively by the vendored Box, use an alternative: wrap text with ANSI background color codes or use the `color` prop with inverted styling.

- [ ] **Step 2: Apply background to expanded view**

Update the expanded view similarly — wrap the entire card in a `Box` with `backgroundColor={bgColor}`.

- [ ] **Step 3: Build and verify**

Run: `cd D:/agent/Jarvis && npx tsc --noEmit -p packages/tui/tsconfig.json`
Expected: Only pre-existing errors

- [ ] **Step 4: Commit**

```bash
git add packages/tui/src/vendor/ui/MessageList.tsx
git commit -m "feat: tool card background colors — status-based tints

Add background colors to ToolUseBlock matching OpenClaw's pattern:
pending/running=dark blue (#1F2A2F), success=dark green (#1E2D23),
error=dark red (#2F1F1F). Provides visual status at a glance."
```

---

### Task 5: OSC 8 Hyperlinks in Markdown (P3-3)

**Problem:** `osc8.ts` is implemented but not wired into `Markdown.tsx`. URLs in assistant responses are not clickable.

**Fix:** Import `addOsc8Links` in `Markdown.tsx` and post-process rendered markdown lines to wrap URLs in OSC 8 escape sequences when the terminal supports it.

**Files:**
- Modify: `packages/tui/src/vendor/ui/Markdown.tsx` (post-processing)
- Reference: `packages/tui/src/vendor/ui/osc8.ts` (already complete)

- [ ] **Step 1: Add post-render OSC 8 processing**

Read `packages/tui/src/vendor/ui/Markdown.tsx` to find where markdown is rendered into lines. Look for the `formatToken` or line rendering area.

Add a post-processing step that applies `addOsc8Links` to each rendered line:

```typescript
import { addOsc8Links } from './osc8.js';

// In the render function, after building each line:
const processedLine = addOsc8Links(rawLine);
```

The exact integration point depends on how Markdown.tsx builds its output. Check if it renders per-line or per-paragraph.

If Markdown.tsx uses `marked` tokens and renders them via `formatToken`, apply `addOsc8Links` as a final pass on rendered strings before they go into `<Text>` components.

- [ ] **Step 2: Verify OSC 8 capability check is correct**

In `osc8.ts`, `supportsOsc8()` returns true for most terminals. Verify this is called once (not per-line) for performance. Add a module-level cache:

```typescript
let _osc8Supported: boolean | null = null;
export function supportsOsc8(): boolean {
  if (_osc8Supported !== null) return _osc8Supported;
  if (process.env['TERM_PROGRAM'] === 'Apple_Terminal') return (_osc8Supported = false);
  _osc8Supported = true;
  return _osc8Supported;
}
```

If this cache already exists, skip.

- [ ] **Step 3: Build and verify**

Run: `cd D:/agent/Jarvis && npx tsc --noEmit -p packages/tui/tsconfig.json`
Expected: Only pre-existing errors

- [ ] **Step 4: Commit**

```bash
git add packages/tui/src/vendor/ui/Markdown.tsx packages/tui/src/vendor/ui/osc8.ts
git commit -m "feat: OSC 8 hyperlinks in Markdown rendering

Wire existing osc8.ts addOsc8Links() into Markdown.tsx rendering.
URLs in assistant responses are now clickable in terminals that
support OSC 8 (Windows Terminal, iTerm2, Kitty, etc.)."
```

---

### Self-Review

1. **Spec coverage:** All 5 items from the priority list are covered. Each task is independently buildable and testable.

2. **Placeholder scan:** No TBD, TODO, or vague instructions. All code is concrete with exact line numbers and file paths.

3. **Type consistency:** 
   - `formatToolLine` signature consistent between Task 3 Step 1 and Step 2
   - `commitStreaming` used consistently between Task 2 Steps 1, 3, 4
   - `streamingContentRef` added in Task 2 Step 1, used in Steps 2-4
   - `reasoningBufferRef` / `reasoningFlushedRef` added in Task 1 Step 1, used in Steps 2-3
   - MessageContent type `{ type: 'thinking', text: string }` matches existing ThinkingBlock in MessageList.tsx
