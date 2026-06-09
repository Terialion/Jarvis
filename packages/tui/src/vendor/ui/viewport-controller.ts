export type ViewportMode = "following" | "history" | "selection";

export type ViewportState = {
  mode: ViewportMode;
  followOutput: boolean;
  hasSelection: boolean;
  interactivePromptActive: boolean;
  scrollDraining: boolean;
};

export type ViewportAction =
  | { type: "user_scrolled" }
  | { type: "selection_changed"; hasSelection: boolean }
  | { type: "interactive_prompt_changed"; interactivePromptActive: boolean }
  | { type: "scroll_draining_changed"; scrollDraining: boolean }
  | { type: "bottom_action" }
  | { type: "resume_follow" };

export function createViewportState(): ViewportState {
  return {
    mode: "following",
    followOutput: true,
    hasSelection: false,
    interactivePromptActive: false,
    scrollDraining: false,
  };
}

function deriveMode(input: {
  followOutput: boolean;
  hasSelection: boolean;
  interactivePromptActive: boolean;
}): ViewportMode {
  const { followOutput, hasSelection, interactivePromptActive } = input;
  if (hasSelection) return "selection";
  if (!followOutput || interactivePromptActive) return "history";
  return "following";
}

export function reduceViewportState(state: ViewportState, action: ViewportAction): ViewportState {
  switch (action.type) {
    case "user_scrolled": {
      return {
        ...state,
        followOutput: false,
        mode: state.hasSelection ? "selection" : "history",
        scrollDraining: true,
      };
    }
    case "selection_changed": {
      const next = {
        ...state,
        hasSelection: action.hasSelection,
      };
      if (action.hasSelection) {
        return {
          ...next,
          followOutput: false,
          mode: "selection",
        };
      }
      return {
        ...next,
        mode: deriveMode({
          followOutput: next.followOutput,
          hasSelection: false,
          interactivePromptActive: next.interactivePromptActive,
        }),
      };
    }
    case "interactive_prompt_changed": {
      const next = {
        ...state,
        interactivePromptActive: action.interactivePromptActive,
      };
      return {
        ...next,
        mode: deriveMode(next),
      };
    }
    case "scroll_draining_changed":
      return {
        ...state,
        scrollDraining: action.scrollDraining,
      };
    case "bottom_action": {
      if (state.hasSelection) {
        return {
          ...state,
          followOutput: false,
          mode: "selection",
        };
      }
      return {
        ...state,
        followOutput: true,
        mode: "following",
      };
    }
    case "resume_follow":
      return {
        ...state,
        followOutput: true,
        mode: "following",
      };
    default:
      return state;
  }
}
