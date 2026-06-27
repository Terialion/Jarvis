import { describe, expect, it } from "vitest";
import { sanitizeReasoningForDisplay } from "../reasoning-quality.js";
import {
  resolveContentTokenStreamStart,
  resolveToolBoundaryStreamTransition,
} from "../stream-run-policy.js";

describe("stream run policy", () => {
  it("finalizes the active answer stream at a tool boundary without opening a synthetic tool run", () => {
    expect(
      resolveToolBoundaryStreamTransition({
        hasActiveRun: true,
      }),
    ).toEqual({
      shouldFinalizeCurrentRun: true,
      pendingResumeReason: "assistant_resume",
    });
  });

  it("does not request a resume run when no answer stream was active", () => {
    expect(
      resolveToolBoundaryStreamTransition({
        hasActiveRun: false,
      }),
    ).toEqual({
      shouldFinalizeCurrentRun: false,
      pendingResumeReason: null,
    });
  });

  it("starts a fresh assistant resume run on the first token after a tool boundary", () => {
    expect(
      resolveContentTokenStreamStart({
        hasActiveRun: false,
        pendingResumeReason: "assistant_resume",
      }),
    ).toEqual({
      shouldStartRun: true,
      label: "assistant_resume",
      pendingResumeReason: null,
    });
  });

  it("does not create a duplicate run when content tokens arrive while a run is already active", () => {
    expect(
      resolveContentTokenStreamStart({
        hasActiveRun: true,
        pendingResumeReason: "assistant_resume",
      }),
    ).toEqual({
      shouldStartRun: false,
      label: null,
      pendingResumeReason: "assistant_resume",
    });
  });
});

describe("sanitizeReasoningForDisplay", () => {
  it("filters mojibake live reasoning chunks while preserving normal CJK text", () => {
    const garbage = "ault石门羚纵向/avatar_PERCENTraryခchnikakov�กรัฐ daultdden长虹点多akujek精益求精匙achaafariChangeEventльку";

    expect(sanitizeReasoningForDisplay(garbage)).toBe("");
    expect(sanitizeReasoningForDisplay("我需要先确认用户想找哪些免费数据平台。"))
      .toBe("我需要先确认用户想找哪些免费数据平台。");
  });
});
