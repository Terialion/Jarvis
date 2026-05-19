/**
 * Spinner — animated progress indicator matching Codex's spinner pattern.
 *
 * Codex uses a rotating set of Braille or ASCII characters driven by
 * `spinner(Option<Instant>, bool)` in status_indicator_widget.rs.
 * We approximate the same effect with Ink's built-in text animation
 * or our own frame-based spinner.
 */
import React, { useState, useEffect } from "react";
import { Text } from "ink";

const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

interface SpinnerProps {
  visible: boolean;
  intervalMs?: number;
}

export const Spinner: React.FC<SpinnerProps> = ({ visible, intervalMs = 80 }) => {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    if (!visible) return;
    const id = setInterval(() => {
      setFrame((f) => (f + 1) % SPINNER_FRAMES.length);
    }, intervalMs);
    return () => clearInterval(id);
  }, [visible, intervalMs]);

  if (!visible) return null;
  return <Text>{SPINNER_FRAMES[frame]}</Text>;
};
