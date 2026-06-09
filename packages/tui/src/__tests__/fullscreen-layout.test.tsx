import React from "react";
import { Writable } from "node:stream";
import { describe, expect, it } from "vitest";
import { Text } from "../vendor/ink-renderer/index.js";
import { renderSync } from "../vendor/ink-renderer/root.js";
import { FullscreenLayout } from "../vendor/ui/FullscreenLayout.js";
import { useSetBottomReplacement, useSetPromptOverlay } from "../vendor/ui/PromptOverlayContext.js";

function renderToString(node: React.ReactNode): string {
  let output = "";
  const stream = new Writable({
    write(chunk: string | Buffer, _encoding: BufferEncoding, callback: (error?: Error | null) => void) {
      output += typeof chunk === "string" ? chunk : chunk.toString("utf8");
      callback();
    },
  });

  const instance = renderSync(node, {
    stdout: stream as unknown as NodeJS.WriteStream,
    stdin: process.stdin,
    stderr: process.stderr,
    exitOnCtrlC: false,
    patchConsole: false,
  });

  instance.unmount();
  try {
    instance.cleanup?.();
  } catch {
    // ignore cleanup noise in tests
  }

  return output;
}

function ReplacementRegistration(): React.ReactNode {
  const replacement = React.useMemo(() => <Text>replacement</Text>, []);
  const overlay = React.useMemo(() => <Text>overlay</Text>, []);
  useSetBottomReplacement(replacement);
  useSetPromptOverlay(overlay);
  return null;
}

describe("FullscreenLayout", () => {
  it("renders bottom replacement instead of the default bottom slot", () => {
    const output = renderToString(
      <FullscreenLayout scrollable={<Text>scrollable</Text>} bottom={<Text>bottom</Text>}>
        <ReplacementRegistration />
      </FullscreenLayout>,
    );

    expect(output).toContain("scrollable");
    expect(output).toContain("overlay");
    expect(output).toContain("replacement");
    expect(output.lastIndexOf("replacement")).toBeGreaterThan(output.lastIndexOf("bottom"));
  });
});
