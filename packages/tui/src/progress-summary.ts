export function humanizeToolName(value: unknown): string {
  const raw = String(value ?? 'tool').trim();
  if (!raw) return 'tool';
  return raw.replace(/[_-]+/g, ' ');
}

export function summarizeAgentEventProgress(event: string, payload: Record<string, unknown>): string | null {
  switch (event) {
    case 'turn:start':
      return 'Opening a new turn';
    case 'skills:matched': {
      const skills = Array.isArray(payload.skills) ? payload.skills : [];
      if (skills.length === 0) return null;
      const names = skills
        .map((item) => (item && typeof item === 'object' ? String((item as Record<string, unknown>).name ?? '') : ''))
        .filter(Boolean)
        .slice(0, 3);
      return names.length > 0 ? `Loaded context from ${names.join(', ')}` : null;
    }
    case 'context:compressing':
      return 'Condensing earlier context';
    case 'llm:request':
      return 'Preparing the next model step';
    case 'llm:response': {
      const toolCallCount = typeof payload.toolCallCount === 'number' ? payload.toolCallCount : 0;
      const contentLength = typeof payload.contentLength === 'number' ? payload.contentLength : 0;
      if (toolCallCount > 0) return `Prepared ${toolCallCount} tool call${toolCallCount > 1 ? 's' : ''}`;
      if (contentLength > 0) return 'Started drafting the response';
      return 'Prepared an empty step';
    }
    case 'tool:executing':
      return `Using ${humanizeToolName(payload.toolName)}`;
    case 'tool:result': {
      const ok = payload.ok === true;
      const toolName = humanizeToolName(payload.toolName);
      return ok ? `Finished ${toolName}` : `Could not use ${toolName}`;
    }
    case 'turn:warning':
      return typeof payload.warning === 'string' ? payload.warning : 'Turn finished with a warning';
    case 'turn:phase': {
      const phase = typeof payload.phase === 'string' ? payload.phase : 'unknown';
      const detail = typeof payload.detail === 'string' ? payload.detail : 'phase_update';
      if (detail === 'enter_finalize') return 'Switching into final answer mode';
      if (detail === 'forcing_final_answer_no_tools' || detail === 'forcing_markdown_answer') {
        return 'Forcing a final answer without more tools';
      }
      if (detail === 'forced_synthesis_after_tool_collection' || detail === 'forcing_synthesis_after_tool_results') {
        return 'Synthesizing a final answer from collected tool results';
      }
      if (detail === 'retry_after_tool_intent_during_finalize') {
        return 'Retrying final answer synthesis without more tools';
      }
      if (detail === 'clearing_stale_plan_mode_state') {
        return 'Clearing stale plan-mode state before continuing';
      }
      if (detail === 'tool_calls_emitted_during_finalize' || detail === 'rejecting_tool_calls_during_finalize') {
        return 'Rejecting extra tool calls during finalization';
      }
      if (detail === 'retry_with_tool_instruction_exhausted_force_choice') {
        return 'Forcing a tool-or-answer choice after repeated tool-intent retries';
      }
      if (detail === 'no_progress_hard_stop') {
        return 'Stopping after repeated low-progress steps';
      }
      return `Turn phase: ${phase}`;
    }
    case 'turn:complete':
      return 'Completed this turn';
    default:
      return null;
  }
}
