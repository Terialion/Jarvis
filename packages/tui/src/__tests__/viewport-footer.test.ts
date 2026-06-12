import { describe, expect, it } from "vitest";
import { buildViewportFooterView } from "../vendor/ui/viewport-footer.js";

describe("buildViewportFooterView", () => {
  it("omits the live footer in following mode", () => {
    const footer = buildViewportFooterView({ mode: "following", isLoading: true });

    expect(footer).toBeNull();
  });

  it("builds a history footer that keeps the viewport pinned in history", () => {
    const footer = buildViewportFooterView({ mode: "history", isLoading: false });
    expect(footer).not.toBeNull();
    if (!footer) {
      throw new Error("expected history footer");
    }

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
    expect(footer).not.toBeNull();
    if (!footer) {
      throw new Error("expected selection footer");
    }

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
