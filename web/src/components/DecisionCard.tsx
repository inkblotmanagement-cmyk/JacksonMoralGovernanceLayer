import type { EvaluateResponse } from '../api'

const LABEL: Record<string, string> = {
  ALLOW: 'Allowed',
  BLOCK: 'Blocked',
  MODIFY: 'Change needed',
  ESCALATE: 'Send to a person',
}

export default function DecisionCard({ result }: { result: EvaluateResponse }) {
  const pct = result.confidence != null ? Math.round(result.confidence * 100) : null
  return (
    <article className={`card decision decision-${result.decision.toLowerCase()}`} aria-labelledby="decision-heading">
      <h2 id="decision-heading">
        <span className="badge">{result.decision}</span> {LABEL[result.decision]}
      </h2>
      <p className="reason">{result.reason}</p>

      {result.suggested_modification ? (
        <div className="callout">
          <h3>Suggested change</h3>
          <p>{result.suggested_modification}</p>
        </div>
      ) : null}

      {result.resources.length ? (
        <div className="callout crisis" role="note">
          <h3>Support resources</h3>
          <ul>{result.resources.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      ) : null}

      <dl className="facts">
        <div>
          <dt>Laws triggered</dt>
          <dd>
            <ul className="laws-list">
              {result.laws_triggered.map((l) => (
                <li key={l.id + l.source}>
                  <strong>{l.id}</strong> <span className="muted">({l.source})</span> {l.statement}
                </li>
              ))}
            </ul>
          </dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>
            {pct != null ? (
              <>
                <meter min={0} max={100} value={pct} aria-label={`Classifier confidence ${pct}%`} /> {pct}%
                <span className="muted"> classifier ({result.classifier_category}); not calibrated</span>
              </>
            ) : (
              <span className="muted">n/a (rules-only verdict)</span>
            )}
          </dd>
        </div>
        {result.grace_force ? (
          <div>
            <dt>Grace Force</dt>
            <dd>
              {result.grace_force.score.toFixed(2)}
              {result.grace_force.threshold != null ? ` (threshold ${result.grace_force.threshold})` : ''}
            </dd>
          </div>
        ) : null}
        <div>
          <dt>Engine</dt>
          <dd>
            {result.engine.mode}
            {result.engine.degraded ? (
              <span className="warn-text"> · degraded: {result.engine.degraded_reason}</span>
            ) : null}
            <span className="muted"> · {result.latency_ms} ms · {result.audited ? 'audited' : 'not audited'}</span>
          </dd>
        </div>
        <div>
          <dt>Decision id</dt>
          <dd><code>{result.id}</code></dd>
        </div>
      </dl>
    </article>
  )
}
