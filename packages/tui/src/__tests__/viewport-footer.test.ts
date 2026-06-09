import { describe, expect, it } from "vitest";
import { buildViewportFooterView } from "../vendor/ui/viewport-footer.js";

describe("buildViewportFooterView", () => {
  it("builds a live footer for streaming output", () => {
    const footer = buildViewportFooterView({ mode: "following", isLoading: true });

    expect(footer.emphasis).toBe(true);
    expect(footer.segments.map((segment) => segment.content)).toEqual([
      "[Live mode]",
      "Following output",
      "Pinned to the newest live step",
    ]);
    expect(footer.segments.map((segment) => segment.color)).toEqual(["green", "green", "gray"]);
  });

  it("builds a history footer that keeps the viewport pinned in history", () => {
    const footer = buildViewportFooterView({ mode: "history", isLoading: false });

    expect(footer.segments.map((segment) => segment.content)).toEqual([
      "[History mode]",
      "Viewing history",
      "New output will not move the viewport",
      "End resumes live output",
    ]);
    expect(footer.segments.map((segment) => segment.color)).toEqual([
      "yellow",
      "yellow",
      "gray",
      "cyan",
    ]);
  });

  it("builds a selection footer that keeps auto behavior frozen", () => {
    const footer = buildViewportFooterView({ mode: "selection", isLoading: false });

    expect(footer.segments.map((segment) => segment.content)).toEqual([
      "[Selection mode]",
      "Selection active",
      "Auto-follow paused",
      "Ctrl+C copies",
      "Esc clears",
    ]);
    expect(footer.segments.map((segment) => segment.color)).toEqual([
      "cyan",
      "cyan",
      "yellow",
      "gray",
      "gray",
    ]);
  });
});
