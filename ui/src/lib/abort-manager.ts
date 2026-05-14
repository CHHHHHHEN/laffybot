/**
 * AbortController manager for session-isolated SSE connections.
 * Each session has its own AbortController for independent cancellation.
 */

const abortControllers = new Map<string, AbortController>()

/**
 * Get or create an AbortController for a session.
 * If the session already has an active controller, returns the existing one.
 */
export function getOrCreateAbortController(sessionId: string): AbortController {
  let controller = abortControllers.get(sessionId)
  if (!controller || controller.signal.aborted) {
    controller = new AbortController()
    abortControllers.set(sessionId, controller)
  }
  return controller
}

/**
 * Get the AbortController for a session, if it exists.
 */
export function getAbortController(sessionId: string): AbortController | undefined {
  return abortControllers.get(sessionId)
}

/**
 * Abort the SSE connection for a session.
 * This will trigger the abort signal and remove the controller.
 */
export function abortSession(sessionId: string): void {
  const controller = abortControllers.get(sessionId)
  if (controller && !controller.signal.aborted) {
    controller.abort()
  }
}

/**
 * Check if a session has an active (non-aborted) AbortController.
 */
export function hasActiveAbortController(sessionId: string): boolean {
  const controller = abortControllers.get(sessionId)
  return controller !== undefined && !controller.signal.aborted
}

/**
 * Clean up the AbortController for a session.
 * Should be called when a session is deleted or when the connection is complete.
 */
export function cleanupAbortController(sessionId: string): void {
  const controller = abortControllers.get(sessionId)
  if (controller && !controller.signal.aborted) {
    controller.abort()
  }
  abortControllers.delete(sessionId)
}

/**
 * Clean up all AbortControllers.
 * Useful for testing or when the app is shutting down.
 */
export function cleanupAllAbortControllers(): void {
  for (const controller of abortControllers.values()) {
    if (!controller.signal.aborted) {
      controller.abort()
    }
  }
  abortControllers.clear()
}
