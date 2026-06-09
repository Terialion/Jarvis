import type { StatusLineSegment } from "./StatusLine.js";
import type { ViewportMode } from "./viewport-mode.js";

export type ViewportFooterView = {
  emphasis: true;
  segments: StatusLineSegment[];
};

export function buildViewportFooterView(input: {
  mode: ViewportMode;
  isLoading: boolean;
}): ViewportFooterView {
  const { mode, isLoading } = input;

  if (mode === "selection") {
    return {
      emphasis: true,
      segments: [
        { content: "[Selection mode]", color: "cyan" },
        { content: "Selection active", color: "cyan" },
        { content: "Auto-follow paused", color: "yellow" },
        { content: "Ctrl+C copies", color: "gray" },
        { content: "Esc clears", color: "gray" },
      ],
    };
  }

  if (mode === "history") {
    return {
      emphasis: true,
      segments: [
        { content: "[History mode]", color: "yellow" },
        { content: "Viewing history", color: "yellow" },
        { content: "New output will not move the viewport", color: "gray" },
        { content: "End resumes live output", color: "cyan" },
      ],
    };
  }

  return {
    emphasis: true,
    segments: [
      { content: "[Live mode]", color: "green" },
      { content: "Following output", color: "green" },
      {
        content: isLoading ? "Pinned to the newest live step" : "Pinned to the latest message",
        color: "gray",
      },
    ],
  };
}
