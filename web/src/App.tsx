import { useEffect, useRef, useState } from 'react'
import { api, getApiKey, type Ready } from './api'
import EvaluatePage from './pages/EvaluatePage'
import LawsPage from './pages/LawsPage'
import AuditPage from './pages/AuditPage'
import SettingsPage from './pages/SettingsPage'

const TABS = [
  { id: 'evaluate', label: 'Evaluate' },
  { id: 'laws', label: 'Laws' },
  { id: 'audit', label: 'Audit log' },
  { id: 'settings', label: 'API key' },
] as const
type TabId = (typeof TABS)[number]['id']

function tabFromHash(): TabId {
  const h = window.location.hash.replace('#/', '').replace('#', '')
  return (TABS.find((t) => t.id === h)?.id ?? 'evaluate') as TabId
}

export default function App() {
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [hasKey, setHasKey] = useState(Boolean(getApiKey()))
  const [ready, setReady] = useState<Ready | null>(null)
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    api.ready().then(setReady).catch(() => setReady(null))
  }, [])

  const go = (id: TabId) => {
    window.history.pushState(null, '', `#/${id}`)
    setTab(id)
    mainRef.current?.focus()
  }

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="site-header">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={32} height={32} />
          <div>
            <h1>JMGL Dashboard</h1>
            <p className="tagline">Jackson Moral Governance Layer · pilot-stage</p>
          </div>
        </div>
        <nav aria-label="Main">
          <ul className="tabs">
            {TABS.map((t) => (
              <li key={t.id}>
                <a href={`#/${t.id}`} aria-current={tab === t.id ? 'page' : undefined}
                   onClick={(e) => { e.preventDefault(); go(t.id) }}>
                  {t.label}
                  {t.id === 'settings' && !hasKey ? <span className="dot" aria-label="(no key set)" /> : null}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      {ready && ready.status !== 'ready' ? (
        <div className="banner warn" role="status">
          {ready.status === 'degraded'
            ? 'The learned classifier is not loaded: the API is answering with the rules only, which miss more harmful requests.'
            : 'The API reports it is not ready. Results may be unavailable.'}
        </div>
      ) : null}
      <main id="main" ref={mainRef} tabIndex={-1}>
        {tab === 'evaluate' && <EvaluatePage hasKey={hasKey} onNeedKey={() => go('settings')} />}
        {tab === 'laws' && <LawsPage />}
        {tab === 'audit' && <AuditPage hasKey={hasKey} onNeedKey={() => go('settings')} />}
        {tab === 'settings' && <SettingsPage onChange={() => setHasKey(Boolean(getApiKey()))} />}
      </main>
      <footer className="site-footer">
        <p>
          JMGL is pilot-stage software. On AI-generated test data it scored 88.1% on held-out cases and missed 1.8% of
          harmful ones, but it flags roughly a quarter of safe requests for review. Keep a person in the loop.
          {ready ? ` API v${ready.version} · ${ready.region}` : ''}
        </p>
      </footer>
    </>
  )
}
