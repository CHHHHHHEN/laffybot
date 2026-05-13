const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body?.error?.code ?? 'UNKNOWN', body?.error?.message ?? 'Request failed')
  }

  return response.json() as Promise<T>
}

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/* ---- Session APIs ---- */

export interface CreateSessionRequest {
  model: string
  system_prompt?: string
  max_iterations?: number
}

export interface SessionResponse {
  session_id: string
  model: string
  status: 'idle' | 'busy' | 'error'
  created_at: string
  message_count?: number
}

export interface ListSessionsResponse {
  sessions: SessionResponse[]
  total: number
  limit: number
  offset: number
}

export function createSession(data: CreateSessionRequest) {
  return apiRequest<SessionResponse>('/api/v1/sessions', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getSession(sessionId: string) {
  return apiRequest<SessionResponse>(`/api/v1/sessions/${sessionId}`)
}

export function listSessions(params?: { limit?: number; offset?: number; status?: string }) {
  const query = new URLSearchParams()
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.offset) query.set('offset', String(params.offset))
  if (params?.status) query.set('status', params.status)
  const qs = query.toString()
  return apiRequest<ListSessionsResponse>(`/api/v1/sessions${qs ? `?${qs}` : ''}`)
}

export function deleteSession(sessionId: string) {
  return apiRequest<{ status: string; session_id: string }>(`/api/v1/sessions/${sessionId}`, {
    method: 'DELETE',
  })
}

/* ---- Message APIs ---- */

export interface SendMessageResponse {
  session_id: string
  request_id: string
}

export interface HistoryMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

export interface HistoryResponse {
  session_id: string
  messages: HistoryMessage[]
}

export function sendMessage(sessionId: string, content: string): Promise<SendMessageResponse> {
  return apiRequest<SendMessageResponse>(`/api/v1/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export function getHistory(sessionId: string, limit = 50) {
  return apiRequest<HistoryResponse>(`/api/v1/sessions/${sessionId}/history?limit=${limit}`)
}

/* ---- Cancel API ---- */

export function cancelRequest(sessionId: string, reason?: string) {
  return apiRequest<{ status: string; session_id: string; request_id: string }>(
    `/api/v1/sessions/${sessionId}/cancel`,
    {
      method: 'POST',
      body: JSON.stringify({ reason: reason ?? 'User cancelled' }),
    }
  )
}

/* ---- SSE API ---- */

export function createSseStream(_sessionId: string, _content: string): EventSource {
  throw new Error('Use connectSseStream for POST-based SSE')
}

export async function connectSseStream(
  sessionId: string,
  content: string,
  onEvent: (event: SseEvent) => void,
  signal: AbortSignal
): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/v1/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
    signal,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body?.error?.code ?? 'UNKNOWN', body?.error?.message ?? 'Request failed')
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    let currentEvent = 'message'
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6).trim()
        if (data === '{}' && currentEvent === 'done') {
          onEvent({ type: 'done' } as SseEvent)
        } else {
          try {
            const parsed = JSON.parse(data) as SseEvent
            onEvent(parsed)
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  }
}

/* ---- Health API ---- */

export function checkHealth() {
  return apiRequest<{ status: string; version: string; timestamp: string }>('/api/v1/health')
}

/* ---- Types ---- */

export type SseEventType =
  | 'session_start'
  | 'content'
  | 'reasoning'
  | 'tool_call'
  | 'tool_result'
  | 'done'
  | 'error'
  | 'cancelled'
  | 'ping'

export interface SseEvent {
  type: SseEventType
  session_id?: string
  request_id?: string
  text?: string
  tool_call_id?: string
  name?: string
  arguments?: Record<string, unknown>
  result?: string
  success?: boolean
  duration_ms?: number
  stop_reason?: string
  usage?: { prompt_tokens: number; completion_tokens: number }
  tools_used?: string[]
  error?: { code: string; message: string; details?: Record<string, unknown> }
  reason?: string
  timestamp?: string
}
