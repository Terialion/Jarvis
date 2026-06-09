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

export function shouldResumeLiveOutputFromBottomAction(hasSelection: boolean): boolean {
  return !hasSelection;
}
