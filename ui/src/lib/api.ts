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
  system_prompt?: string
  max_iterations?: number
  provider_id?: string
  model_name?: string
}

export interface SessionResponse {
  session_id: string
  provider_id: string
  model_name: string
  status: 'idle' | 'busy' | 'error'
  created_at: string
  message_count?: number
  title?: string | null
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

export interface UpdateSessionTitleRequest {
  title: string
}

export function updateSessionTitle(sessionId: string, title: string) {
  return apiRequest<SessionResponse>(`/api/v1/sessions/${sessionId}/title`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
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

/* ---- Global Events API ---- */

export interface GlobalEvent {
  type: 'title_update' | 'ping'
  session_id?: string
  title?: string
  timestamp?: string
}

export async function connectGlobalEvents(
  onEvent: (event: GlobalEvent) => void,
  signal: AbortSignal
): Promise<void> {
  console.log('[connectGlobalEvents] Fetching SSE endpoint')
  const response = await fetch(`${BASE_URL}/api/v1/events`, {
    method: 'GET',
    signal,
  })

  if (!response.ok) {
    console.error('[connectGlobalEvents] Failed to connect:', response.status, response.statusText)
    throw new ApiError(response.status, 'CONNECTION_ERROR', 'Failed to connect to global events')
  }

  console.log('[connectGlobalEvents] SSE connection established')

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      console.log('[connectGlobalEvents] Stream ended')
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    let currentEvent = 'ping'
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6).trim()
        try {
          const parsed = JSON.parse(data)
          // Map the event based on SSE event type field
          if (currentEvent === 'title_update') {
            console.log('[connectGlobalEvents] Parsed title_update event:', parsed)
            onEvent({
              type: 'title_update',
              session_id: parsed.session_id,
              title: parsed.title,
            })
          } else if (currentEvent === 'ping') {
            onEvent({ type: 'ping', timestamp: parsed.timestamp })
          }
        } catch {
          // skip malformed JSON
          console.warn('[connectGlobalEvents] Failed to parse SSE data:', data)
        }
      }
    }
  }
}

/* ---- Provider APIs ---- */

export interface ProviderResponse {
  id: string
  name: string
  base_url: string
  has_api_key: boolean
  created_at: string
}

export interface ProviderDetailResponse extends ProviderResponse {
  extra_headers: Record<string, string>
}

export interface ProviderCreateRequest {
  name: string
  base_url: string
  api_key: string
  extra_headers?: Record<string, string>
}

export interface ProviderUpdateRequest {
  name?: string
  base_url?: string
  api_key?: string
  extra_headers?: Record<string, string>
}

export interface ModelResponse {
  id: string
  provider_id: string
  name: string
}

export interface UpdateSessionModelRequest {
  provider_id: string
  model_name: string
}

export interface TestResultResponse {
  success: boolean
  message: string
  latency_ms: number | null
}

export function listProviders() {
  return apiRequest<ProviderResponse[]>('/api/v1/providers')
}

export function createProvider(data: ProviderCreateRequest) {
  return apiRequest<ProviderResponse>('/api/v1/providers', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getProvider(id: string) {
  return apiRequest<ProviderDetailResponse>(`/api/v1/providers/${id}`)
}

export function updateProvider(id: string, data: ProviderUpdateRequest) {
  return apiRequest<ProviderResponse>(`/api/v1/providers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteProvider(id: string) {
  return apiRequest<{ status: string; provider_id: string }>(
    `/api/v1/providers/${id}`,
    { method: 'DELETE' }
  )
}

export function listModels(providerId: string) {
  return apiRequest<ModelResponse[]>(`/api/v1/providers/${providerId}/models`)
}

export function addModel(providerId: string, data: { name: string }) {
  return apiRequest<ModelResponse>(`/api/v1/providers/${providerId}/models`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteModel(providerId: string, modelId: string) {
  return apiRequest<{ status: string; model_id: string }>(`/api/v1/providers/${providerId}/models/${modelId}`, {
    method: 'DELETE',
  })
}

export function updateSessionModel(sessionId: string, data: UpdateSessionModelRequest) {
  return apiRequest<SessionResponse>(`/api/v1/sessions/${sessionId}/model`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function testProvider(id: string) {
  return apiRequest<TestResultResponse>(`/api/v1/providers/${id}/test`, {
    method: 'POST',
  })
}

export interface DefaultSessionModelResponse {
  provider_id: string
  model_name: string
}

export function getDefaultSessionModel() {
  return apiRequest<DefaultSessionModelResponse | null>('/api/v1/settings/default-session-model')
}

export function setDefaultSessionModel(data: { provider_id: string; model_name: string }) {
  return apiRequest<void>('/api/v1/settings/default-session-model', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function clearDefaultSessionModel() {
  return apiRequest<void>('/api/v1/settings/default-session-model', {
    method: 'DELETE',
  })
}

export interface SummaryModelResponse {
  provider_id: string
  model_name: string
}

export function getSummaryModel() {
  return apiRequest<SummaryModelResponse | null>('/api/v1/settings/summary-model')
}

export function setSummaryModel(data: { provider_id: string; model_name: string }) {
  return apiRequest<void>('/api/v1/settings/summary-model', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function clearSummaryModel() {
  return apiRequest<void>('/api/v1/settings/summary-model', {
    method: 'DELETE',
  })
}

/* ---- Health API ---- */

export function checkHealth() {
  return apiRequest<{ status: string; version: string; timestamp: string }>('/api/v1/health')
}

/* ---- Tools API ---- */

export interface ToolInfoWithStatus {
  name: string
  description: string
  read_only: boolean
  enabled: boolean
}

export function listTools() {
  return apiRequest<ToolInfoWithStatus[]>('/api/v1/tools')
}

export function enableTool(name: string) {
  return apiRequest<{ name: string; enabled: boolean }>(`/api/v1/tools/${name}/enable`, {
    method: 'POST',
  })
}

export function disableTool(name: string) {
  return apiRequest<{ name: string; enabled: boolean }>(`/api/v1/tools/${name}/disable`, {
    method: 'POST',
  })
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
  | 'title_update'

export interface SseEvent {
  type: SseEventType
  session_id?: string
  request_id?: string
  text?: string
  title?: string
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
