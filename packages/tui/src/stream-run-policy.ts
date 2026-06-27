export type PendingStreamResumeReason = "assistant_resume" | null;

export function resolveToolBoundaryStreamTransition(input: {
  hasActiveRun: boolean;
}): {
  shouldFinalizeCurrentRun: boolean;
  pendingResumeReason: PendingStreamResumeReason;
} {
  if (!input.hasActiveRun) {
    return {
      shouldFinalizeCurrentRun: false,
      pendingResumeReason: null,
    };
  }

  return {
    shouldFinalizeCurrentRun: true,
    pendingResumeReason: "assistant_resume",
  };
}

export function resolveContentTokenStreamStart(input: {
  hasActiveRun: boolean;
  pendingResumeReason: PendingStreamResumeReason;
}): {
  shouldStartRun: boolean;
  label: string | null;
  pendingResumeReason: PendingStreamResumeReason;
} {
  if (input.hasActiveRun) {
    return {
      shouldStartRun: false,
      label: null,
      pendingResumeReason: input.pendingResumeReason,
    };
  }

  if (input.pendingResumeReason) {
    return {
      shouldStartRun: true,
      label: input.pendingResumeReason,
      pendingResumeReason: null,
    };
  }

  return {
    shouldStartRun: false,
    label: null,
    pendingResumeReason: null,
  };
}
