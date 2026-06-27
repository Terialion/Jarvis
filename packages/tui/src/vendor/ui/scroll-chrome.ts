import type { ViewportMode } from "./viewport-mode.js";

export type ScrollChromeState = {
  active: boolean;
  baselineItemCount: number;
  baselineScrollHeight: number;
  unseenCount: number;
  shouldRequestFollow: boolean;
};

export function createScrollChromeState(): ScrollChromeState {
  return {
    active: false,
    baselineItemCount: 0,
    baselineScrollHeight: 0,
    unseenCount: 0,
    shouldRequestFollow: false,
  };
}

export function clearScrollChrome(_state: ScrollChromeState): ScrollChromeState {
  return createScrollChromeState();
}

export function areScrollChromeStatesEqual(a: ScrollChromeState, b: ScrollChromeState): boolean {
  return (
    a.active === b.active &&
    a.baselineItemCount === b.baselineItemCount &&
    a.baselineScrollHeight === b.baselineScrollHeight &&
    a.unseenCount === b.unseenCount &&
    a.shouldRequestFollow === b.shouldRequestFollow
  );
}

export function recordScrollChromeSnapshot(
  state: ScrollChromeState,
  input: {
    mode: ViewportMode;
    itemCount: number;
    scrollHeight: number;
    viewportHeight: number;
    scrollTop: number;
  },
): ScrollChromeState {
  if (state.active) {
    return state;
  }

  if (input.mode === "following") {
    return clearScrollChrome(state);
  }

  const maxScrollTop = Math.max(0, input.scrollHeight - input.viewportHeight);
  const isAwayFromBottom = maxScrollTop - input.scrollTop > 0;
  if (!isAwayFromBottom) {
    return clearScrollChrome(state);
  }

  return {
    active: true,
    baselineItemCount: Math.max(0, input.itemCount),
    baselineScrollHeight: Math.max(0, input.scrollHeight),
    unseenCount: 0,
    shouldRequestFollow: false,
  };
}

export function recordScrollChromeTranscriptMutation(
  state: ScrollChromeState,
  input: {
    mode: ViewportMode;
    itemCount: number;
    scrollHeight: number;
  },
): ScrollChromeState {
  if (input.mode === "following") {
    return clearScrollChrome(state);
  }

  if (!state.active) {
    return state;
  }

  return {
    ...state,
    unseenCount: Math.max(0, input.itemCount - state.baselineItemCount),
    baselineScrollHeight: Math.max(state.baselineScrollHeight, input.scrollHeight),
    shouldRequestFollow: false,
  };
}

export function shouldShowJumpToBottomPill(state: ScrollChromeState): boolean {
  return state.active;
}

export function formatJumpToBottomLabel(state: ScrollChromeState): string {
  if (state.unseenCount <= 0) {
    return "Jump to bottom | End";
  }
  const noun = state.unseenCount === 1 ? "message" : "messages";
  return `${state.unseenCount} new ${noun} | End to jump`;
}
