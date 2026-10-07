import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, apiBase, getApiKey, request, setApiKey } from './api'

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status, headers }))
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('api client', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    window.__JMGL_CONFIG__ = { apiBaseUrl: '' }
  })
  afterEach(() => vi.unstubAllGlobals())

  it('stores keys per session unless remembered', () => {
    setApiKey('k1', false)
    expect(sessionStorage.getItem('jmgl.apiKey')).toBe('k1')
    expect(localStorage.getItem('jmgl.apiKey')).toBeNull()
    setApiKey('k2', true)
    expect(getApiKey()).toBe('k2')
    expect(sessionStorage.getItem('jmgl.apiKey')).toBeNull()
    setApiKey('', false)
    expect(getApiKey()).toBe('')
  })

  it('uses runtime base URL and sends the key header', async () => {
    window.__JMGL_CONFIG__ = { apiBaseUrl: 'https://api.example.org/' }
    expect(apiBase()).toBe('https://api.example.org')
    setApiKey('secret', false)
    const f = mockFetch(200, { decision: 'BLOCK' })
    const r = await api.evaluate('x', ['h1'], 'rules')
    expect(r.decision).toBe('BLOCK')
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('https://api.example.org/v1/evaluate')
    expect(new Headers(init.headers).get('X-API-Key')).toBe('secret')
    expect(JSON.parse(init.body as string)).toEqual({ action: 'x', context: { history: ['h1'] }, mode: 'rules' })
  })

  it('maps errors to friendly messages', async () => {
    mockFetch(401, { detail: 'Missing or invalid API key' })
    await expect(request('/v1/laws')).rejects.toMatchObject({ status: 401 })
    mockFetch(429, { detail: 'Rate limit exceeded' }, { 'Retry-After': '12' })
    const err = (await request('/v1/laws').catch((e) => e)) as ApiError
    expect(err.message).toContain('12 seconds')
    expect(err.retryAfter).toBe(12)
    mockFetch(422, { detail: [{ loc: ['body', 'action'], msg: 'String should have at least 1 character' }] })
    await expect(request('/v1/evaluate')).rejects.toThrow('action: String should have at least 1 character')
  })

  it('treats a 503 readiness answer as data', async () => {
    mockFetch(503, { status: 'not_ready' })
    await expect(api.ready()).resolves.toMatchObject({ status: 'not_ready' })
  })

  it('reports network failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('fail') }))
    await expect(request('/healthz')).rejects.toMatchObject({ status: 0 })
  })

  it('builds audit query strings', async () => {
    const f = mockFetch(200, { items: [], backend: 'sql' })
    await api.audit({ limit: 10, cursor: '42', decision: 'BLOCK' })
    expect((f.mock.calls[0] as unknown as [string])[0]).toBe('/v1/audit?limit=10&cursor=42&decision=BLOCK')
  })
})
