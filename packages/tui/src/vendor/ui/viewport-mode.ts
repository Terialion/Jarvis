export type ViewportMode = "following" | "history" | "selection";

export function getViewportMode(input: {
  followOutput: boolean;
  hasSelection: boolean;
  interactivePromptActive: boolean;
}): ViewportMode {
  const { followOutput, hasSelection, interactivePromptActive } = input;
  if (hasSelection) return "selection";
  if (interactivePromptActive || !followOutput) return "history";
  return "following";
}

export function shouldAutoResumeFollow(input: {
  followOutput: boolean;
  hasSelection: boolean;
  interactivePromptActive: boolean;
  isLoading: boolean;
  remainingScrollDistance: number;
}): boolean {
  void input;
  // CC-style rule: once the user leaves live follow, we do not implicitly
  // resume it based on layout/measurement heuristics. Only an explicit bottom
  // action (End / scroll:bottom) can opt back into live output.
  return false;
}

export function shouldAutoScrollToBottomOnContentUpdate(input: {
  followOutput: boolean;
  hasSelection: boolean;
  interactivePromptActive: boolean;
  scrollDraining: boolean;
  remainingScrollDistance: number;
}): boolean {
  const {
    followOutput,
    hasSelection,
    interactivePromptActive,
    scrollDraining,
    remainingScrollDistance,
  } = input;
  if (!followOutput || hasSelection || interactivePromptActive || scrollDraining) {
    return false;
  }

  return remainingScrollDistance <= 3;
}

export function isUserViewportScrollMutationSource(mutationSource: string | undefined): boolean {
  if (!mutationSource) return false;
  if (mutationSource === "imperative_scroll_bottom") return false;
  if (mutationSource === "render_follow") return false;
  return (
    mutationSource === "imperative_scroll_by" ||
    mutationSource === "imperative_scroll_to" ||
    mutationSource === "imperative_scroll_to_element" ||
    mutationSource === "render_scroll_anchor"
  );
}
export function shouldResumeLiveOutputFromBottomAction(hasSelection: boolean): boolean {
  return !hasSelection;
}

export function resolveViewportTopForFollowState(input: {
  followOutput: boolean;
  scrollTop: number;
  scrollHeight: number;
  viewportHeight: number;
  pendingDelta?: number;
}): number {
  const { followOutput, scrollTop, scrollHeight, viewportHeight, pendingDelta = 0 } = input;
  const maxScroll = Math.max(0, scrollHeight - viewportHeight);
  if (followOutput && pendingDelta >= 0) {
    return maxScroll;
  }

  return Math.max(0, Math.min(maxScroll, scrollTop + pendingDelta));
}
