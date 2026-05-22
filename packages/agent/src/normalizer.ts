// ============================================================================
// Message normalizer — provider-specific message formatting
// Python ref: src/jarvis/agent/message_normalizer.py
// ============================================================================

// ============================================================================
// Types
// ============================================================================

export interface MessageRecord {
  role: string;
  content: string;
  [key: string]: unknown;
}

// ============================================================================
// Main entry point
// ============================================================================

export function normalizeMessages(
  messages: MessageRecord[],
  opts?: {
    provider?: string;
    model?: string;
  },
): MessageRecord[] {
  if (messages.length === 0) return messages;

  const providerL = (opts?.provider ?? '').toLowerCase();
  const modelL = (opts?.model ?? '').toLowerCase();

  // Step 1: Move all system messages to the front, merging into one
  let result = consolidateSystemMessages(messages);

  // Step 2: Provider-specific rules
  if (providerL === 'qwen') {
    result = qwenNormalize(result);
  }

  if (providerL === 'deepseek') {
    result = deepseekNormalize(result, modelL);
  }

  return result;
}

// ============================================================================
// Consolidate system messages
// ============================================================================

function consolidateSystemMessages(messages: MessageRecord[]): MessageRecord[] {
  const systemContents: string[] = [];
  let hasSeenNonSystem = false;
  const out: MessageRecord[] = [];

  for (const m of messages) {
    const role = String(m.role ?? '');

    if (role === 'system') {
      if (!hasSeenNonSystem) {
        systemContents.push(String(m.content ?? ''));
      } else {
        // Mid-conversation system message — convert to user
        out.push({ ...m, role: 'user' });
      }
    } else {
      hasSeenNonSystem = true;
      out.push(m);
    }
  }

  if (systemContents.length > 0) {
    out.unshift({ role: 'system', content: systemContents.join('\n\n') });
  }

  return out;
}

// ============================================================================
// Qwen normalization
// ============================================================================

function qwenNormalize(messages: MessageRecord[]): MessageRecord[] {
  // Qwen requires system messages only at the beginning.
  // consolidateSystemMessages already handles this. Additional rule:
  // ensure there are no consecutive user messages (merge them).
  return mergeConsecutiveSameRole(messages, new Set(['user']));
}

// ============================================================================
// DeepSeek normalization
// ============================================================================

function deepseekNormalize(messages: MessageRecord[], modelL: string): MessageRecord[] {
  const isReasoner = modelL.includes('reasoner');

  let result = messages;
  if (isReasoner) {
    // DeepSeek reasoner: system prompt can cause issues.
    // Prepend system content into the first user message.
    result = mergeSystemIntoFirstUser(result);
  }

  // Merge consecutive same-role messages
  result = mergeConsecutiveSameRole(result, new Set(['user', 'assistant']));

  return result;
}

// ============================================================================
// Helpers
// ============================================================================

function mergeSystemIntoFirstUser(messages: MessageRecord[]): MessageRecord[] {
  if (messages.length === 0 || messages[0].role !== 'system') {
    return messages;
  }

  const systemContent = String(messages[0].content ?? '');
  const result = messages.slice(1); // Remove system message

  // Find first user message
  for (const m of result) {
    if (m.role === 'user') {
      m.content = systemContent + '\n\n' + String(m.content ?? '');
      return result;
    }
  }

  // No user message found — unlikely, but insert one
  result.unshift({ role: 'user', content: systemContent });
  return result;
}

function mergeConsecutiveSameRole(
  messages: MessageRecord[],
  roles: Set<string>,
): MessageRecord[] {
  if (messages.length === 0) return messages;

  const out: MessageRecord[] = [messages[0]];
  for (let i = 1; i < messages.length; i++) {
    const m = messages[i];
    const role = String(m.role ?? '');
    const content = String(m.content ?? '');
    const prev = out[out.length - 1];
    const prevRole = String(prev.role ?? '');

    if (role === prevRole && roles.has(role)) {
      prev.content = String(prev.content ?? '') + '\n\n' + content;
    } else {
      out.push(m);
    }
  }

  return out;
}
