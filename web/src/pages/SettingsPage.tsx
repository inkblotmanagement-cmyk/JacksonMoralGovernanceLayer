import { useState, type FormEvent } from 'react'
import { api, ApiError, apiBase, getApiKey, isKeyRemembered, setApiKey } from '../api'

export default function SettingsPage({ onChange }: { onChange: () => void }) {
  const [key, setKey] = useState(getApiKey())
  const [remember, setRemember] = useState(isKeyRemembered())
  const [status, setStatus] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [show, setShow] = useState(false)

  async function save(e: FormEvent) {
    e.preventDefault()
    const k = key.trim()
    if (!k) {
      setApiKey('', false)
      setStatus({ kind: 'ok', text: 'Key removed from this browser.' })
      onChange()
      return
    }
    try {
      const who = await api.authCheck(k)
      setApiKey(k, remember)
      setStatus({ kind: 'ok', text: `Key accepted (${who.role} key, id ${who.key_id}).` })
    } catch (err) {
      setStatus({ kind: 'error', text: err instanceof ApiError ? err.message : String(err) })
    }
    onChange()
  }

  return (
    <section aria-labelledby="settings-heading">
      <h2 id="settings-heading">API key</h2>
      <form onSubmit={save} className="card form">
        <label htmlFor="api-key">JMGL API key</label>
        <div className="row">
          <input id="api-key" type={show ? 'text' : 'password'} autoComplete="off" spellCheck={false}
                 value={key} onChange={(e) => setKey(e.target.value)} aria-describedby="key-help" />
          <button type="button" className="secondary" onClick={() => setShow(!show)} aria-pressed={show}>
            {show ? 'Hide' : 'Show'}
          </button>
        </div>
        <p id="key-help" className="help">
          Ask your JMGL administrator for a key. Client keys can evaluate; admin keys can also read the audit log.
          The key is kept only in this browser tab unless you choose to remember it.
        </p>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Remember on this device (avoid on shared computers)
        </label>
        <div className="row">
          <button type="submit">Save and verify</button>
          <button type="button" className="secondary" onClick={() => { setKey(''); setApiKey('', false); onChange(); setStatus({ kind: 'ok', text: 'Key removed from this browser.' }) }}>
            Forget key
          </button>
        </div>
        <div aria-live="polite">
          {status ? <p className={`banner ${status.kind === 'ok' ? 'success' : 'error'}`}>{status.text}</p> : null}
        </div>
        <p className="muted small">API: <code>{apiBase() || window.location.origin}</code></p>
      </form>
    </section>
  )
}
