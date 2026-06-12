import { describe, expect, it } from "vitest";
import { isStandaloneRunningToolMessage, type Message } from "../vendor/ui/MessageList.js";

describe("MessageList live item extraction", () => {
  it("detects standalone running tool messages", () => {
    const message: Message = {
      id: "tool_1",
      role: "assistant",
      content: [
        {
          type: "tool_use",
          toolName: "bash",
          input: "echo hi",
          status: "running",
        },
      ],
    };

    expect(isStandaloneRunningToolMessage(message)).toBe(true);
  });

  it("keeps completed tool messages in the historical list", () => {
    const message: Message = {
      id: "tool_1",
      role: "assistant",
      content: [
        {
          type: "tool_use",
          toolName: "bash",
          input: "echo hi",
          status: "success",
          result: "hi",
        },
      ],
    };

    expect(isStandaloneRunningToolMessage(message)).toBe(false);
  });

  it("does not extract mixed-content assistant messages", () => {
    const message: Message = {
      id: "assistant_1",
      role: "assistant",
      content: [
        { type: "text", text: "hello" },
        {
          type: "tool_use",
          toolName: "bash",
          input: "echo hi",
          status: "running",
        },
      ],
    };

    expect(isStandaloneRunningToolMessage(message)).toBe(false);
  });
});
