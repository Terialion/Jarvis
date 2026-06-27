import React from "react";
import { Writable } from "node:stream";
import { describe, expect, it } from "vitest";
import { Text, type ScrollBoxHandle } from "../vendor/ink-renderer/index.js";
import { renderSync } from "../vendor/ink-renderer/root.js";
import { TranscriptViewport } from "../vendor/ui/TranscriptViewport.js";

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

function Harness({ onReady }: { onReady: () => void }): React.ReactNode {
  const scrollRef = React.useRef<ScrollBoxHandle | null>(null);
  return (
    <TranscriptViewport
      scrollRef={scrollRef}
      onScrollHandleReady={onReady}
      items={[
        {
          id: "one",
          render: () => <Text>one</Text>,
        },
      ]}
    />
  );
}

describe("TranscriptViewport ref lifecycle", () => {
  it("notifies when the ScrollBox handle is attached", () => {
    let readyCount = 0;

    renderToString(<Harness onReady={() => readyCount++} />);

    expect(readyCount).toBeGreaterThan(0);
  });
});
