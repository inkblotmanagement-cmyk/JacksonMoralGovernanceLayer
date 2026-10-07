import { useEffect, useState } from 'react'
import { api, ApiError, type LawsResponse } from '../api'

export default function LawsPage() {
  const [data, setData] = useState<LawsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    api.laws().then(setData).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  }, [])

  const laws = (data?.laws ?? []).filter((l) =>
    `${l.id} ${l.statement} ${l.harm ?? ''}`.toLowerCase().includes(q.toLowerCase()),
  )

  return (
    <section aria-labelledby="laws-heading">
      <h2 id="laws-heading">Laws in force</h2>
      {data?.status ? <p className="muted">Status: {data.status}</p> : null}
      <label htmlFor="law-filter">Filter laws</label>
      <input id="law-filter" type="search" value={q} onChange={(e) => setQ(e.target.value)} />
      {error ? <p className="banner error" role="alert">{error}</p> : null}
      {!data && !error ? <p aria-live="polite">Loading…</p> : null}
      <ul className="law-cards">
        {laws.map((l) => (
          <li key={l.id} className="card">
            <h3><span className={`badge small decision-${l.default_decision.toLowerCase()}`}>{l.default_decision}</span> {l.id}</h3>
            <p>{l.statement}</p>
            {l.harm ? <p className="muted">Covers: {l.harm}</p> : null}
          </li>
        ))}
      </ul>
      {data ? <p className="muted small">laws.json SHA-256: <code>{data.laws_sha256}</code></p> : null}
    </section>
  )
}
