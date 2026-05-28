import type { ThreadEvent } from '@jarvis/agent';
import type { Message } from '../vendor/ui/MessageList.js';

export type TuiPresentationMode = 'claude' | 'codex';

export type ClaudeTranscriptState = {
  mode: 'claude';
  messages: Message[];
};

export type CodexTimelineState = {
  mode: 'codex';
  events: ThreadEvent[];
};

export type TuiPresentationState =
  | ClaudeTranscriptState
  | CodexTimelineState;
