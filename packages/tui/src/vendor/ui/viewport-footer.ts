import type { StatusLineSegment } from "./StatusLine.js";
import type { ViewportMode } from "./viewport-mode.js";

export type ViewportFooterView = {
  emphasis: true;
  segments: StatusLineSegment[];
};

export function buildViewportFooterView(input: {
  mode: ViewportMode;
  isLoading: boolean;
}): ViewportFooterView | null {
  const { mode, isLoading } = input;

  if (mode === "selection") {
    return {
      emphasis: true,
      segments: [
        { content: "Selection", color: "cyan" },
        { content: "Follow paused", color: "yellow" },
        { content: "Ctrl+C copies", color: "gray" },
        { content: "Esc clears", color: "gray" },
      ],
    };
  }

  if (mode === "history") {
    return {
      emphasis: true,
      segments: [
        { content: "History", color: "yellow" },
        { content: "New output stays put", color: "gray" },
        { content: "End resumes", color: "cyan" },
      ],
    };
  }

  void isLoading;
  return null;
}
