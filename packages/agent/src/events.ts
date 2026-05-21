// ============================================================================
// AgentEventBus — lightweight typed event emitter for agent lifecycle events
// ============================================================================

import type { AgentEvent } from '@jarvis/shared';

// ============================================================================
// Types
// ============================================================================

export type EventHandler = (payload: Record<string, unknown>) => void;

// ============================================================================
// AgentEventBus
// ============================================================================

export class AgentEventBus {
  private _handlers = new Map<string, Set<EventHandler>>();

  /**
   * Register an event handler.
   * Multiple handlers can be registered for the same event.
   */
  on(event: string, handler: EventHandler): void {
    if (!this._handlers.has(event)) {
      this._handlers.set(event, new Set());
    }
    this._handlers.get(event)!.add(handler);
  }

  /**
   * Remove a previously registered event handler.
   * No-op if the handler was not registered.
   */
  off(event: string, handler: EventHandler): void {
    this._handlers.get(event)?.delete(handler);
  }

  /**
   * Emit an event to all registered handlers.
   * Handlers are called synchronously. Errors in handlers are caught and logged
   * but do not prevent other handlers from running.
   */
  emit(event: string, payload: Record<string, unknown>): void {
    const handlers = this._handlers.get(event);
    if (!handlers || handlers.size === 0) return;

    for (const handler of handlers) {
      try {
        handler(payload);
      } catch (err) {
        console.error(
          `[AgentEventBus] Error in handler for event "${event}":`,
          err,
        );
      }
    }
  }

  /**
   * Create an AgentEvent object with an auto-generated eventId.
   */
  static createEvent(
    type: string,
    turnId: string,
    payload: Record<string, unknown> = {},
  ): AgentEvent {
    return {
      type,
      turnId,
      payload,
      eventId: `evt_${crypto.randomUUID()}`,
    };
  }

  /**
   * Remove all handlers for all events.
   */
  clear(): void {
    this._handlers.clear();
  }

  /**
   * Get the number of registered handlers for an event.
   */
  listenerCount(event: string): number {
    return this._handlers.get(event)?.size ?? 0;
  }
}
