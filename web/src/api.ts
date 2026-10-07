// Typed client for the JMGL v1 API.
export type Decision = 'ALLOW' | 'BLOCK' | 'MODIFY' | 'ESCALATE'
export type Mode = 'ensemble' | 'rules'

export interface LawRef { id: string; statement: string; source: 'rules' | 'classifier' | 'default' }
export interface GraceForce { score: number; threshold?: number | null; passed?: boolean | null; rewritten?: boolean | null; components: Record<string, unknown> }
export interface EngineInfo {
  mode: Mode
  requested_mode: Mode
  engine_version: string
  ensemble_version?: string | null
  model_loaded: boolean
  degraded: boolean
  degraded_reason?: string | null
}
export interface EvaluateResponse {
  id: string
  decision: Decision
  rule_id: string
  laws_triggered: LawRef[]
  reason: string
  suggested_modification?: string | null
  resources: string[]
  confidence?: number | null
  classifier_category?: string | null
  grace_force?: GraceForce | null
  engine: EngineInfo
  signals?: Record<string, number> | null
  latency_ms: number
  audited: boolean
}
export interface Law { id: string; statement: string; harm?: string | null; default_decision: Decision }
export interface LawsResponse { spec_version?: string | null; status?: string | null; laws_sha256: string; laws: Law[] }
export interface AuditRecord {
  seq: number
  id: string
  timestamp: string
  decision: Decision
  rule_id: string
  laws_triggered: string[]
  mode: Mode
  degraded: boolean
  confidence?: number | null
  grace_force?: number | null
  input_sha256: string
  input_raw?: string | null
  key_id: string
  region: string
  engine_version: string
}
export interface AuditPage { items: AuditRecord[]; next_cursor?: string | null; backend: string }
export interface Ready {
  status: 'ready' | 'degraded' | 'not_ready'
  version: string
  engine_mode: Mode
  model_loaded: boolean
  model_error?: string | null
  audit_backend: string
  audit_ok: boolean
  region: string
}
export interface AuthCheck { valid: boolean; role: 'client' | 'admin'; key_id: string }

export class ApiError extends Error {
  status: number
  requestId?: string
  retryAfter?: number
  constructor(status: number, message: string, requestId?: string, retryAfter?: number) {
    super(message)
    this.status = status
    this.requestId = requestId
    this.retryAfter = retryAfter
  }
}

export function apiBase(): string {
  const runtime = typeof window !== 'undefined' ? window.__JMGL_CONFIG__?.apiBaseUrl : undefined
  const built = import.meta.env.VITE_API_BASE_URL as string | undefined
  return (runtime || built || '').replace(/\/+$/, '')
}

// ---- API key storage: session-only by default; "remember" opts in to localStorage.
const KEY = 'jmgl.apiKey'
export function getApiKey(): string {
  return sessionStorage.getItem(KEY) ?? localStorage.getItem(KEY) ?? ''
}
export function setApiKey(key: string, remember: boolean): void {
  sessionStorage.removeItem(KEY)
  localStorage.removeItem(KEY)
  if (!key) return
  if (remember) localStorage.setItem(KEY, key)
  else sessionStorage.setItem(KEY, key)
}
export function isKeyRemembered(): boolean {
  return localStorage.getItem(KEY) !== null
}

function describe(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const e = d as { loc?: unknown[]; msg?: string }
        return `${(e.loc ?? []).filter((x) => x !== 'body').join('.')}: ${e.msg ?? ''}`
      })
      .join('; ')
  }
  return 'Request failed'
}

export async function request<T>(path: string, init: RequestInit = {}, key = getApiKey()): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  if (key) headers.set('X-API-Key', key)
  let res: Response
  try {
    res = await fetch(apiBase() + path, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the JMGL API. Check the API URL and your connection.')
  }
  const text = await res.text()
  let body: unknown
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!res.ok && !(path === '/readyz' && res.status === 503)) {
    const detail = (body as { detail?: unknown } | null)?.detail
    const retry = res.headers.get('Retry-After')
    const msg =
      res.status === 401 ? 'Missing or invalid API key. Add a key in Settings.'
      : res.status === 403 ? 'This key is not allowed to do that (admin key required).'
      : res.status === 429 ? `Rate limit reached. Try again in ${retry ?? 'a few'} seconds.`
      : describe(detail)
    throw new ApiError(res.status, msg, res.headers.get('X-Request-ID') ?? undefined, retry ? Number(retry) : undefined)
  }
  return body as T
}

export const api = {
  evaluate: (action: string, history: string[], mode?: Mode) =>
    request<EvaluateResponse>('/v1/evaluate', {
      method: 'POST',
      body: JSON.stringify({ action, context: { history }, ...(mode ? { mode } : {}) }),
    }),
  laws: () => request<LawsResponse>('/v1/laws'),
  audit: (params: { limit?: number; cursor?: string | null; decision?: string; rule_id?: string }) => {
    const q = new URLSearchParams()
    q.set('limit', String(params.limit ?? 25))
    if (params.cursor) q.set('cursor', params.cursor)
    if (params.decision) q.set('decision', params.decision)
    if (params.rule_id) q.set('rule_id', params.rule_id)
    return request<AuditPage>(`/v1/audit?${q.toString()}`)
  },
  ready: () => request<Ready>('/readyz'),
  authCheck: (key: string) => request<AuthCheck>('/v1/auth/check', {}, key),
}
