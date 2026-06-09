import React, { createContext, useContext, useLayoutEffect, useMemo, useState, type ReactNode } from "react";

type PromptOverlaySlots = {
  overlay: ReactNode | null;
  modal: ReactNode | null;
  bottomFloat: ReactNode | null;
  bottomReplacement: ReactNode | null;
};

type PromptOverlayApi = PromptOverlaySlots & {
  setOverlay: (node: ReactNode | null) => void;
  setModal: (node: ReactNode | null) => void;
  setBottomFloat: (node: ReactNode | null) => void;
  setBottomReplacement: (node: ReactNode | null) => void;
};

const PromptOverlayContext = createContext<PromptOverlayApi | null>(null);

export function PromptOverlayProvider({ children }: { children?: ReactNode }): ReactNode {
  const [overlay, setOverlay] = useState<ReactNode | null>(null);
  const [modal, setModal] = useState<ReactNode | null>(null);
  const [bottomFloat, setBottomFloat] = useState<ReactNode | null>(null);
  const [bottomReplacement, setBottomReplacement] = useState<ReactNode | null>(null);

  const value = useMemo(
    () => ({
      overlay,
      modal,
      bottomFloat,
      bottomReplacement,
      setOverlay,
      setModal,
      setBottomFloat,
      setBottomReplacement,
    }),
    [bottomFloat, bottomReplacement, modal, overlay],
  );

  return <PromptOverlayContext.Provider value={value}>{children}</PromptOverlayContext.Provider>;
}

function usePromptOverlayContext(): PromptOverlayApi {
  const value = useContext(PromptOverlayContext);
  if (!value) {
    throw new Error("PromptOverlayContext is not available");
  }
  return value;
}

export function usePromptOverlaySlots(): PromptOverlaySlots {
  const { overlay, modal, bottomFloat, bottomReplacement } = usePromptOverlayContext();
  return { overlay, modal, bottomFloat, bottomReplacement };
}

export function useSetPromptOverlay(node: ReactNode | null): void {
  const { setOverlay } = usePromptOverlayContext();
  useLayoutEffect(() => {
    setOverlay(node);
    return () => setOverlay(null);
  }, [node, setOverlay]);
}

export function useSetPromptModal(node: ReactNode | null): void {
  const { setModal } = usePromptOverlayContext();
  useLayoutEffect(() => {
    setModal(node);
    return () => setModal(null);
  }, [node, setModal]);
}

export function useSetBottomFloat(node: ReactNode | null): void {
  const { setBottomFloat } = usePromptOverlayContext();
  useLayoutEffect(() => {
    setBottomFloat(node);
    return () => setBottomFloat(null);
  }, [node, setBottomFloat]);
}

export function useSetBottomReplacement(node: ReactNode | null): void {
  const { setBottomReplacement } = usePromptOverlayContext();
  useLayoutEffect(() => {
    setBottomReplacement(node);
    return () => setBottomReplacement(null);
  }, [node, setBottomReplacement]);
}
