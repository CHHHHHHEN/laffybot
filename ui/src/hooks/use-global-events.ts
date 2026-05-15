import { useEffect, useRef } from 'react'
import type { InfiniteData } from '@tanstack/react-query'
import { useQueryClient } from '@tanstack/react-query'
import { connectGlobalEvents, type GlobalEvent, type SessionResponse } from '@/lib/api'

interface SessionsPage {
  sessions: SessionResponse[]
  total: number
  limit: number
  offset: number
}

/**
 * Hook for managing global SSE event connection.
 *
 * Establishes a persistent connection to /api/v1/events on app startup
 * and handles title_update events by directly updating the sessions cache.
 *
 * Features:
 * - Auto-reconnect with exponential backoff on disconnect
 * - Handles title_update events by updating sessions cache directly
 * - Ignores ping events (heartbeat)
 */
export function useGlobalEvents() {
  const queryClient = useQueryClient()
  const abortControllerRef = useRef<AbortController | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const reconnectAttemptsRef = useRef(0)

  useEffect(() => {
    const connect = async () => {
      // Create new AbortController for this connection
      abortControllerRef.current = new AbortController()
      const signal = abortControllerRef.current.signal

      console.log('[useGlobalEvents] Attempting to connect to SSE endpoint')

      try {
        await connectGlobalEvents(
          (event: GlobalEvent) => {
            console.log('[useGlobalEvents] Received event:', event.type, event)
            if (event.type === 'title_update' && event.session_id && event.title !== undefined) {
              // Directly update sessions cache for immediate UI update
              queryClient.setQueryData<InfiniteData<SessionsPage>>(
                ['sessions'],
                (old) => {
                  if (!old?.pages) return old
                  return {
                    ...old,
                    pages: old.pages.map((page) => ({
                      ...page,
                      sessions: page.sessions.map((s) =>
                        s.session_id === event.session_id ? { ...s, title: event.title } : s
                      ),
                    })),
                  }
                }
              )
            }
            // Ignore ping events (heartbeat)
          },
          signal
        )
        console.log('[useGlobalEvents] Connection closed normally')
      } catch (error) {
        // Connection closed or aborted
        if (signal.aborted) {
          // Clean disconnect, don't reconnect
          console.log('[useGlobalEvents] Connection aborted (clean disconnect)')
          return
        }

        // Unexpected disconnect, schedule reconnect with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
        reconnectAttemptsRef.current += 1

        console.error(
          '[useGlobalEvents] Connection error:',
          error,
          `- Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`
        )

        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect()
        }, delay)
      }
    }

    // Start connection on mount
    connect()

    // Cleanup on unmount
    return () => {
      console.log('[useGlobalEvents] Cleaning up connection')
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [queryClient])
}