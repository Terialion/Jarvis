# Context Management Fix — Message Roles & Session Continuity

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix context message roles so conversation history uses native `user/assistant/tool` role sequences instead of flattening tool results into `role: 'user'`, and ensure `tool_call_id` metadata flows correctly through the entire context pipeline.

**Architecture:** Four targeted fixes: (1) `ContextBuilder.buildMessages()` preserves `tool_call_id`/`name` when converting `ChatMessage` → `LLMMessage`, (2) `PromptBuilder.buildMessages()` emits history with native roles (`tool` + `tool_call_id` instead of `user`), matching API expectations, (3) `AgentLoop.run()` — the simple code path already uses `ContextBuilder.buildMessages()` so it benefits automatically from fix 1, but `runTurn()` sends `LLMMessage[]` directly — verify the pipeline, (4) add `UserFactExtractor` to auto-extract user identity from conversation turns.

**Tech Stack:** TypeScript, Vitest, `@jarvis/agent`, `@jarvis/shared`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `packages/agent/src/context.ts` | Modify | Fix `buildMessages()` metadata, add `UserFactExtractor` |
| `packages/agent/src/prompt-builder.ts` | Modify | Native-role history, `tool_call_id` on tool messages |
| `packages/agent/src/__tests__/context.test.ts` | Modify | Add tests for metadata preservation + fact extraction |
| `packages/agent/src/__tests__/prompt-builder.test.ts` | Create | Tests for native-role history output |

---

### Task 1: Fix `ContextBuilder.buildMessages()` — preserve metadata

**Files:**
- Modify: `packages/agent/src/context.ts:168-188`

- [ ] **Step 1: Write the failing test**

Add to `packages/agent/src/__tests__/context.test.ts` after the existing "buildMessages handles tool messages with toolCallId" test (around line 352):

```typescript
  it('buildMessages preserves tool_call_id and name in LLM output', () => {
    const history: ChatMessage[] = [
      {
        role: 'tool',
        content: 'file contents here',
        messageId: 'msg_t1',
        toolCallId: 'call_read_1',
        name: 'read',
      },
      {
        role: 'assistant',
        content: 'I read the file',
        messageId: 'msg_a1',
      },
    ];

    const messages = builder.buildMessages('system', history);

    // Tool message must have tool_call_id and name
    expect(messages[1].role).toBe('tool');
    expect(messages[1].content).toBe('file contents here');
    expect(messages[1].tool_call_id).toBe('call_read_1');
    expect(messages[1].name).toBe('read');

    // Assistant message must NOT have spurious tool_call_id
    expect(messages[2].role).toBe('assistant');
    expect(messages[2].tool_call_id).toBeUndefined();
    expect(messages[2].name).toBeUndefined();
  });

  it('buildMessages handles messages without optional fields', () => {
    const history: ChatMessage[] = [
      { role: 'user', content: 'hello', messageId: 'm1' },
      { role: 'assistant', content: 'hi', messageId: 'm2' },
    ];

    const messages = builder.buildMessages('system', history);

    expect(messages[1].tool_call_id).toBeUndefined();
    expect(messages[1].name).toBeUndefined();
    expect(messages[2].tool_call_id).toBeUndefined();
    expect(messages[2].name).toBeUndefined();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run packages/agent/src/__tests__/context.test.ts -t "preserves tool_call_id"`
Expected: FAIL — `tool_call_id` is `undefined`

- [ ] **Step 3: Fix `buildMessages()` in `context.ts`**

Replace lines 177-186 in `packages/agent/src/context.ts`:

```typescript
    for (const msg of history) {
      const llmMsg: LLMMessage = {
        role: msg.role,
        content: msg.content,
      };
      if (msg.toolCallId) {
        llmMsg.tool_call_id = msg.toolCallId;
      }
      if (msg.name) {
        llmMsg.name = msg.name;
      }
      messages.push(llmMsg);
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run packages/agent/src/__tests__/context.test.ts`
Expected: All 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agent/src/context.ts packages/agent/src/__tests__/context.test.ts
git commit -m "fix: preserve tool_call_id and name in ContextBuilder.buildMessages()"
```

---

### Task 2: Fix `PromptBuilder.buildMessages()` — native-role history

**Files:**
- Modify: `packages/agent/src/prompt-builder.ts`

- [ ] **Step 1: Create the test file**

Create `packages/agent/src/__tests__/prompt-builder.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { PromptBuilder } from '../prompt-builder.js';
import type { TurnContext } from '../context.js';

function makeTurnContext(overrides: Partial<TurnContext> = {}): TurnContext {
  return {
    userInput: 'current request',
    cwd: '/test',
    modelProvider: null,
    modelName: 'test-model',
    permissionMode: 'workspace_write',
    contextPack: {
      project: {
        cwd: '/test',
        repoRoot: '/test',
        projectName: 'test',
        projectFilesHint: [],
        projectInstructions: null,
      },
      conversation: {
        threadId: null,
        turnId: 'turn_1',
        recentMessages: [],
        compactedSummary: null,
      },
      memory: { shortTerm: {}, longTermRefs: [] },
      skills: {
        availableSkills: [],
        loadedSkills: [],
        skillObservations: [],
        researchObservations: [],
        activeTask: null,
      },
      tokenBudget: {},
      warnings: [],
    },
    modelBackend: null,
    projectId: null,
    sessionId: null,
    turnId: null,
    ...overrides,
  };
}

describe('PromptBuilder', () => {
  const builder = new PromptBuilder();

  it('emits tool results with role=tool and tool_call_id', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [
            { role: 'user', content: 'read foo.ts' },
            { role: 'assistant', content: 'Reading...' },
            {
              role: 'tool',
              content: 'export const x = 1;',
              tool_call_id: 'call_abc',
              metadata: { tool_name: 'read' },
            },
          ],
          compactedSummary: null,
        },
      },
    });

    const messages = builder.buildMessages(ctx);

    // Find the tool message
    const toolMsgs = messages.filter((m) => m.role === 'tool');
    expect(toolMsgs.length).toBe(1);
    expect(toolMsgs[0].tool_call_id).toBe('call_abc');
    expect(toolMsgs[0].content).toContain('read');
    expect(toolMsgs[0].content).toContain('export const x = 1;');
  });

  it('preserves user and assistant roles natively', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [
            { role: 'user', content: 'hello' },
            { role: 'assistant', content: 'hi there' },
            { role: 'user', content: 'how are you' },
            { role: 'assistant', content: 'doing well' },
          ],
          compactedSummary: null,
        },
      },
    });

    const messages = builder.buildMessages(ctx);

    const roles = messages.map((m) => m.role);
    // system -> (skills maybe) -> system (history banner) -> user -> assistant -> user -> assistant -> user (current)
    expect(roles.filter((r) => r === 'user').length).toBe(3); // 2 history + 1 current
    expect(roles.filter((r) => r === 'assistant').length).toBe(2);
  });

  it('does not include tool_call_id on non-tool messages', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [
            { role: 'user', content: 'hello' },
            { role: 'assistant', content: 'hi' },
          ],
          compactedSummary: null,
        },
      },
    });

    const messages = builder.buildMessages(ctx);
    for (const m of messages) {
      if (m.role !== 'tool') {
        expect(m.tool_call_id).toBeUndefined();
      }
    }
  });

  it('handles empty history gracefully', () => {
    const ctx = makeTurnContext();

    const messages = builder.buildMessages(ctx);
    expect(messages.length).toBeGreaterThan(0);
    expect(messages[messages.length - 1].role).toBe('user');
    expect(messages[messages.length - 1].content).toContain('current request');
  });

  it('injects compaction summary when present', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [],
          compactedSummary: 'User asked to refactor auth, decided to use JWT.',
        },
      },
    });

    const messages = builder.buildMessages(ctx);
    const summaryMsg = messages.find((m) => m.content.includes('conversation-summary'));
    expect(summaryMsg).toBeDefined();
    expect(summaryMsg!.content).toContain('JWT');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run packages/agent/src/__tests__/prompt-builder.test.ts`
Expected: FAIL — tool messages have `role: 'user'` instead of `role: 'tool'`

- [ ] **Step 3: Fix `PromptBuilder.buildMessages()`**

In `packages/agent/src/prompt-builder.ts`, change line 48 signature to include `tool_call_id`:

```typescript
  buildMessages(turnContext: TurnContext): Array<{ role: string; content: string; tool_call_id?: string }> {
```

Replace lines 89-121 (the history injection and message loop):

```typescript
    // Inject recent conversation history as native-role messages.
    const recent = [...conv.recentMessages].slice(-40);
    if (recent.length > 0) {
      messages.push({
        role: 'system',
        content:
          '<conversation-history>\n' +
          'Messages above this point are from earlier turns in ' +
          'this session. They are provided for continuity so you ' +
          'know what was discussed. The user\'s CURRENT request ' +
          'is the LAST message below.\n' +
          '</conversation-history>',
      });
    }

    for (const msg of recent) {
      const role = (msg.role ?? '').trim();
      const content = String(msg.content ?? '');
      if (!role || !content) continue;

      if (role === 'tool') {
        const toolName =
          ((msg.metadata as Record<string, unknown> | undefined)?.['tool_name'] as string) ??
          (msg.tool_call_id as string) ??
          'unknown';
        messages.push({
          role: 'tool',
          tool_call_id: msg.tool_call_id,
          content: `[Previous tool result — ${toolName}]: ${content.slice(0, 3000)}`,
        });
      } else {
        messages.push({ role, content });
      }
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run packages/agent/src/__tests__/prompt-builder.test.ts`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agent/src/prompt-builder.ts packages/agent/src/__tests__/prompt-builder.test.ts
git commit -m "fix: emit history with native tool role and tool_call_id in PromptBuilder"
```

---

### Task 3: Verify full pipeline — `AgentLoop.run()` and `runTurn()`

**Files:**
- Verify: `packages/agent/src/loop.ts`
- Modify: `packages/agent/src/__tests__/agent.test.ts` (add assertion)

- [ ] **Step 1: Add assertion to existing agent test**

In `packages/agent/src/__tests__/agent.test.ts`, add a new test after "includes history in messages" (around line 870):

```typescript
  it('sends tool history messages with role=tool and tool_call_id', async () => {
    const mockProvider = createMockProvider([
      { content: 'Understood, continuing...', finishReason: 'stop' },
    ]);

    const loop = new AgentLoop({
      model: { model: 'test-model' },
      provider: mockProvider as unknown as LLMProvider,
    });

    const history: ChatMessage[] = [
      { role: 'user', content: 'Read the config', messageId: 'm_u1' },
      {
        role: 'assistant',
        content: 'Let me read it',
        messageId: 'm_a1',
      },
      {
        role: 'tool',
        content: '{"port": 3000}',
        messageId: 'm_t1',
        toolCallId: 'call_read_cfg',
        name: 'read',
      },
    ];

    await loop.run('Check that config', history);

    const callArgs = mockProvider.chat.mock.calls[0];
    const messages = callArgs[0] as Array<{
      role: string;
      content: string;
      tool_call_id?: string;
      name?: string;
    }>;

    // Find the tool message
    const toolMsg = messages.find((m) => m.role === 'tool');
    expect(toolMsg).toBeDefined();
    expect(toolMsg!.tool_call_id).toBe('call_read_cfg');
    expect(toolMsg!.name).toBe('read');
    expect(toolMsg!.content).toContain('port');
  });
```

- [ ] **Step 2: Run test to verify it passes (Task 1 already fixed `buildMessages()`)**

Run: `npx vitest run packages/agent/src/__tests__/agent.test.ts -t "tool history messages"`
Expected: PASS — because Task 1 already fixed `ContextBuilder.buildMessages()` to preserve `tool_call_id`

- [ ] **Step 3: Run all agent tests to verify no regressions**

Run: `npx vitest run packages/agent/src/__tests__/`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add packages/agent/src/__tests__/agent.test.ts
git commit -m "test: add assertion for native tool role in AgentLoop.run() history"
```

---

### Task 4: Add `UserFactExtractor` — auto-extract user identity

**Files:**
- Modify: `packages/agent/src/context.ts` — add `UserFactExtractor` class

- [ ] **Step 1: Write the failing test**

Add to `packages/agent/src/__tests__/context.test.ts`:

```typescript
import { UserFactExtractor } from '../context.js';

// ... at end of file:

describe('UserFactExtractor', () => {
  it('extracts name from "my name is" pattern', () => {
    const facts = UserFactExtractor.extractFacts('Hello, my name is Zhang Wei. I need help with code.');
    const nameFact = facts.find((f) => f.key === 'name');
    expect(nameFact).toBeDefined();
    expect(nameFact!.value).toBe('Zhang Wei');
    expect(nameFact!.memory_type).toBe('user_profile');
  });

  it('extracts name from "call me" pattern', () => {
    const facts = UserFactExtractor.extractFacts('You can call me Alice when we chat.');
    const nameFact = facts.find((f) => f.key === 'name');
    expect(nameFact).toBeDefined();
    expect(nameFact!.value).toBe('Alice');
  });

  it('extracts name from "I\'m" pattern', () => {
    const facts = UserFactExtractor.extractFacts("Hi, I'm Bob Smith and I work here.");
    const nameFact = facts.find((f) => f.key === 'name');
    expect(nameFact).toBeDefined();
    expect(nameFact!.value).toBe('Bob Smith');
  });

  it('extracts role from "I\'m a developer" pattern', () => {
    const facts = UserFactExtractor.extractFacts("I'm a software engineer working on the backend team.");
    const roleFact = facts.find((f) => f.key === 'role');
    expect(roleFact).toBeDefined();
    expect(roleFact!.value).toContain('software engineer');
    expect(roleFact!.memory_type).toBe('user_profile');
  });

  it('returns empty array for text with no identifiable facts', () => {
    const facts = UserFactExtractor.extractFacts('Can you fix the bug in auth.ts?');
    expect(facts).toEqual([]);
  });

  it('does not match "I\'m" in code contexts', () => {
    const facts = UserFactExtractor.extractFacts(
      "I'm checking if I'm logged in. The config says I'm using the wrong port.",
    );
    // "I'm checking", "I'm logged", "I'm using" — none are identity statements
    expect(facts).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run packages/agent/src/__tests__/context.test.ts -t "UserFactExtractor"`
Expected: FAIL — `UserFactExtractor` is not exported

- [ ] **Step 3: Add `UserFactExtractor` to `context.ts`**

Add after the `PromptBuilderShim` class (after line 1101 in context.ts):

```typescript
// ============================================================================
// UserFactExtractor — lightweight extraction of user profile from turns
// ============================================================================

export class UserFactExtractor {
  private static NAME_PATTERNS: Array<{ pattern: RegExp; group: number }> = [
    { pattern: /my name is\s+["']?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)["']?/i, group: 1 },
    { pattern: /call me\s+["']?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)["']?/i, group: 1 },
    { pattern: /i(?:'| a)?m\s+["']?([A-Z][a-z]+(?:\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))["']?(?:\s|,|\.|$)/i, group: 1 },
  ];

  private static ROLE_PATTERN = /i(?:'|\s+a)?m\s+(a\s+)?((?:senior\s+|lead\s+|staff\s+|principal\s+)?(?:software\s+)?(?:engineer|developer|programmer|architect|designer|manager|lead|cto|devops|sre|data\s+scientist|researcher|student|consultant|product\s+manager))/i;

  private static CODE_CONTEXT_NOUNS = /\b(config|file|code|function|variable|port|server|api|endpoint|route|module|class|bug|error|test|log|user|admin)\b/i;

  static extractFacts(text: string): Array<{ key: string; value: string; memory_type: string }> {
    const facts: Array<{ key: string; value: string; memory_type: string }> = [];

    // Name extraction
    for (const { pattern, group } of UserFactExtractor.NAME_PATTERNS) {
      const match = text.match(pattern);
      if (match) {
        const captured = match[group]?.trim();
        if (captured && captured.length >= 2 && captured.length <= 40) {
          // Avoid false positives: single words that are common code nouns
          if (!captured.includes(' ') && UserFactExtractor.CODE_CONTEXT_NOUNS.test(captured)) {
            continue;
          }
          facts.push({ key: 'name', value: captured, memory_type: 'user_profile' });
          break;
        }
      }
    }

    // Role extraction
    const roleMatch = text.match(UserFactExtractor.ROLE_PATTERN);
    if (roleMatch) {
      const roleValue = roleMatch[0].trim();
      // Must be a real identity statement, not "I'm checking the port"
      if (/^i(?:'|\s+a)?m\s+(a\s+)?(senior|lead|staff|principal|software|engineer|developer|programmer|architect|designer|manager|cto|devops|sre|data|researcher|student|consultant|product)/i.test(roleValue)) {
        facts.push({ key: 'role', value: roleValue, memory_type: 'user_profile' });
      }
    }

    return facts;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run packages/agent/src/__tests__/context.test.ts -t "UserFactExtractor"`
Expected: All 6 UserFactExtractor tests PASS

- [ ] **Step 5: Run the full test suite**

Run: `npx vitest run packages/agent/src/__tests__/`
Expected: All tests PASS (22+ tests)

- [ ] **Step 6: Commit**

```bash
git add packages/agent/src/context.ts packages/agent/src/__tests__/context.test.ts
git commit -m "feat: add UserFactExtractor for auto-extracting user identity from conversation"
```

---

## Self-Review

**1. Spec coverage:**
- Fix `ContextBuilder.buildMessages()` metadata → Task 1
- Fix `PromptBuilder.buildMessages()` native roles → Task 2
- Verify `AgentLoop.run()` pipeline → Task 3
- User fact extraction → Task 4

**2. Placeholder scan:** No TBD, TODO, or "add appropriate error handling" patterns. All code is concrete.

**3. Type consistency:**
- `LLMMessage` already has `tool_call_id?: string` and `name?: string` — confirmed in `model.ts:55-65`
- `PromptBuilder.buildMessages()` return type updated to `Array<{ role: string; content: string; tool_call_id?: string }>`
- `UserFactExtractor.extractFacts()` returns `Array<{ key: string; value: string; memory_type: string }>` — consistent with memory store expectations
- `ChatMessage.toolCallId` (camelCase) maps to `LLMMessage.tool_call_id` (snake_case) — mirroring existing pattern