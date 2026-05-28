// ============================================================================
// StreamCursor — blinking cursor at end of streaming text (Hermes pattern)
// ============================================================================
// 420ms toggle, matching Hermes StreamCursor.tsx behavior

import { Text } from '../ink-renderer/index.js';
import { useState, useEffect } from 'react';

export function StreamCursor({
  visible = true,
  streaming = false,
  color,
}: {
  visible?: boolean;
  streaming?: boolean;
  color?: string;
}) {
  const [on, setOn] = useState(true);

  useEffect(() => {
    if (!visible || !streaming) {
      setOn(true);
      return;
    }
    const id = setInterval(() => setOn((v) => !v), 420);
    return () => clearInterval(id);
  }, [streaming, visible]);

  if (!visible) return null;

  if (streaming) {
    return <Text color={color}>{on ? '▍' : ' '}</Text>;
  }
  return null;
}