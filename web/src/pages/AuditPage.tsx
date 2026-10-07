import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type AuditRecord } from '../api'

const DECISIONS = ['', 'ALLOW', 'BLOCK', 'MODIFY', 'ESCALATE']

export default function AuditPage({ hasKey, onNeedKey }: { hasKey: boolean; onNeedKey: () => void }) {
  const [items, setItems] = useState<AuditRecord[]>([])
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [next, setNext] = useState<string | null>(null)
  const [decision, setDecision] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)

  const [reload, setReload] = useState(0)

  const show = useCallback((p: Promise<{ items: AuditRecord[]; next_cursor?: string | null }>) =>
    p.then((page) => { setItems(page.items); setNext(page.next_cursor ?? null); setError(null) })
      .catch((e) => { setItems([]); setError(e instanceof ApiError ? e.message : String(e)) })
      .finally(() => setBusy(false)), [])

  // First page: refetch when the key, the filter, or the refresh counter changes.
  useEffect(() => {
    if (!hasKey) return
    void show(api.audit({ limit: 25, decision: decision || undefined }))
  }, [hasKey, decision, reload, show])

  const load = (cursor: string | null) => {
    setBusy(true)
    void show(api.audit({ limit: 25, cursor, decision: decision || undefined }))
  }

  if (!hasKey) {
    return (
      <section aria-labelledby="audit-heading">
        <h2 id="audit-heading">Audit log</h2>
        <p className="banner info">An admin API key is required. <button type="button" className="link" onClick={onNeedKey}>Add a key</button></p>
      </section>
    )
  }

  const page = cursors.length
  return (
    <section aria-labelledby="audit-heading">
      <h2 id="audit-heading">Audit log</h2>
      <p className="muted">Newest first. Inputs appear as hashes unless raw logging was explicitly enabled on the server.</p>
      <div className="row">
        <label htmlFor="decision-filter">Decision</label>
        <select id="decision-filter" value={decision} onChange={(e) => { setCursors([null]); setBusy(true); setDecision(e.target.value) }}>
          {DECISIONS.map((d) => <option key={d} value={d}>{d || 'All'}</option>)}
        </select>
        <button type="button" onClick={() => { setCursors([null]); setBusy(true); setReload((n) => n + 1) }} disabled={busy}>Refresh</button>
      </div>
      {error ? <p className="banner error" role="alert">{error}</p> : null}
      <div className="table-wrap" aria-busy={busy}>
        <table>
          <caption className="sr-only">Audit records, page {page}</caption>
          <thead>
            <tr><th scope="col">Time</th><th scope="col">Decision</th><th scope="col">Law</th><th scope="col">Engine</th><th scope="col">Confidence</th><th scope="col">Input</th></tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td data-label="Time"><time dateTime={r.timestamp}>{new Date(r.timestamp).toLocaleString()}</time></td>
                <td data-label="Decision"><span className={`badge small decision-${r.decision.toLowerCase()}`}>{r.decision}</span></td>
                <td data-label="Law">{r.laws_triggered.join(', ') || r.rule_id}</td>
                <td data-label="Engine">{r.mode}{r.degraded ? ' (degraded)' : ''}</td>
                <td data-label="Confidence">{r.confidence != null ? `${Math.round(r.confidence * 100)}%` : '—'}</td>
                <td data-label="Input">{r.input_raw ? r.input_raw : <code title={r.input_sha256}>{r.input_sha256.slice(0, 12)}…</code>}</td>
              </tr>
            ))}
            {!items.length && !busy && !error ? <tr><td colSpan={6}>No records.</td></tr> : null}
          </tbody>
        </table>
      </div>
      <nav className="row" aria-label="Audit pagination">
        <button type="button" disabled={busy || page <= 1}
                onClick={() => { const c = cursors.slice(0, -1); setCursors(c); load(c[c.length - 1]) }}>
          Newer
        </button>
        <span aria-live="polite">Page {page}</span>
        <button type="button" disabled={busy || !next}
                onClick={() => { setCursors([...cursors, next]); load(next) }}>
          Older
        </button>
      </nav>
    </section>
  )
}
