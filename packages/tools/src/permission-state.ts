// ============================================================================
// PermissionStateMachine — context-aware permission state tracking
// ============================================================================
// Tracks the agent's current phase and automatically adjusts permission
// behavior. Integrates with PermissionManager to enforce state-based policies.
//
// States:
//   idle → exploring → executing → idle (happy path)
//   exploring → questioning → awaiting_confirm → executing (question flow)
//   exploring → planning → awaiting_review → executing (plan flow)
// ============================================================================

import { PermissionManager, type PermissionMode } from './runtime.js';

// ============================================================================
// Types
// ============================================================================

export type PermissionState =
  | 'idle'              // Waiting for user input
  | 'exploring'         // Agent is reading/exploring (after user submit)
  | 'planning'          // Agent entered plan mode
  | 'awaiting_review'   // Agent presented plan, waiting for user approval
  | 'questioning'       // Agent asked a question, waiting for user answer
  | 'awaiting_confirm'  // Agent answered question, waiting for user confirmation
  | 'executing';        // Agent is actively executing (write/bash allowed)

export type PermissionEvent =
  | { type: 'user_submit' }
  | { type: 'tool_call'; toolName: string }
  | { type: 'enter_plan_mode' }
  | { type: 'exit_plan_mode' }
  | { type: 'ask_user_question' }
  | { type: 'user_answer' }
  | { type: 'user_approve_plan' }
  | { type: 'user_reject_plan' }
  | { type: 'user_confirm' }
  | { type: 'turn_complete' }
  | { type: 'set_state'; state: PermissionState };

export type StateChangeCallback = (
  state: PermissionState,
  previous: PermissionState,
) => void;

// ============================================================================
// State transition table
// ============================================================================

const TRANSITIONS: Record<PermissionState, Partial<Record<PermissionEvent['type'], PermissionState>>> = {
  idle: {
    user_submit: 'exploring',
  },
  exploring: {
    tool_call: 'exploring',        // stay exploring on most tool calls
    enter_plan_mode: 'planning',
    ask_user_question: 'questioning',
    turn_complete: 'idle',
  },
  planning: {
    exit_plan_mode: 'awaiting_review',
    turn_complete: 'idle',
  },
  awaiting_review: {
    user_approve_plan: 'executing',
    user_reject_plan: 'planning',
    turn_complete: 'idle',
  },
  questioning: {
    user_answer: 'awaiting_confirm',
    turn_complete: 'idle',
  },
  awaiting_confirm: {
    user_confirm: 'executing',
    turn_complete: 'idle',
  },
  executing: {
    tool_call: 'executing',
    enter_plan_mode: 'planning',
    ask_user_question: 'questioning',
    turn_complete: 'idle',
  },
};

// ============================================================================
// State → permission mode mapping
// ============================================================================

const STATE_MODE_OVERRIDE: Partial<Record<PermissionState, PermissionMode>> = {
  questioning: 'plan',           // read-only while waiting for answer
  planning: 'plan',              // read-only in plan mode
  awaiting_review: 'plan',       // read-only while reviewing plan
  awaiting_confirm: 'plan',      // read-only while confirming
};

// ============================================================================
// PermissionStateMachine
// ============================================================================

export class PermissionStateMachine {
  private state: PermissionState = 'idle';
  private previousState: PermissionState = 'idle';
  private baseMode: PermissionMode = 'default';
  private listeners: StateChangeCallback[] = [];
  private permManager?: PermissionManager;

  constructor(options?: { permissionManager?: PermissionManager; initialMode?: PermissionMode }) {
    this.permManager = options?.permissionManager;
    this.baseMode = options?.initialMode ?? 'default';
  }

  /** Get current state. */
  getState(): PermissionState {
    return this.state;
  }

  /** Get the user's base permission mode (before state overrides). */
  getBaseMode(): PermissionMode {
    return this.baseMode;
  }

  /** Set the user's base permission mode. */
  setBaseMode(mode: PermissionMode): void {
    this.baseMode = mode;
    this.syncMode();
  }

  /** Get the effective permission mode (base mode + state override). */
  getEffectiveMode(): PermissionMode {
    return STATE_MODE_OVERRIDE[this.state] ?? this.baseMode;
  }

  /** Subscribe to state changes. Returns unsubscribe function. */
  onStateChange(callback: StateChangeCallback): () => void {
    this.listeners.push(callback);
    return () => {
      const idx = this.listeners.indexOf(callback);
      if (idx !== -1) this.listeners.splice(idx, 1);
    };
  }

  /** Transition to a new state based on an event. */
  transition(event: PermissionEvent): void {
    // Handle set_state override
    if (event.type === 'set_state') {
      this.setState(event.state);
      return;
    }

    const transitions = TRANSITIONS[this.state];
    const nextState = transitions?.[event.type];

    if (nextState) {
      this.setState(nextState);
    }
  }

  /** Force-set the state (bypasses transition table). */
  private setState(next: PermissionState): void {
    if (next === this.state) return;
    this.previousState = this.state;
    this.state = next;
    this.syncMode();
    for (const cb of this.listeners) {
      try { cb(next, this.previousState); } catch { /* listener error */ }
    }
  }

  /** Sync the effective mode to the PermissionManager. */
  private syncMode(): void {
    if (this.permManager) {
      const effective = this.getEffectiveMode();
      this.permManager.setMode(effective);
    }
  }

  /** Reset to idle state. */
  reset(): void {
    this.setState('idle');
  }
}
