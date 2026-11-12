import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { evaluateRepository, validRepository } from './api'
import type { Evaluation, Status } from './api'
import './App.css'

const names: Record<Status, string> = { healthy: 'Healthy', warning: 'Review', critical: 'Critical', unknown: 'Unknown' }
function Badge({ status }: { status: Status }) { return <span className={`badge ${status}`}>{names[status]}</span> }
function date(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Date unavailable'
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(value))
}
function Card({ title, status, children }: { title: string; status: Status; children: ReactNode }) {
  return <article className="metric"><div className="card-heading"><h3>{title}</h3><Badge status={status} /></div>{children}</article>
}
function Results({ data }: { data: Evaluation }) {
  const { repository: repo, assessment, metrics: m, meta } = data
  const github = repo.url?.startsWith('https://github.com/') ? repo.url : null
  return <section aria-label="Evaluation results" className="results">
    <div className="repo-heading"><div><p className="eyebrow">Repository report</p><h2>{repo.full_name ?? 'Repository'}</h2>
      {repo.description && <p>{repo.description}</p>}</div>
      {github && <a href={github} target="_blank" rel="noreferrer">View on GitHub ↗</a>}
    </div>
    <div className="repo-meta"><span>{repo.stars === null ? 'Stars unavailable' : `☆ ${repo.stars.toLocaleString()} stars`}</span><span>Branch: {repo.default_branch ?? 'Unknown'}</span></div>
    {meta.errors.length > 0 && <div className="notice" role="status"><strong>Partial results</strong> — Some information could not be retrieved from GitHub. Available signals are shown below; unknown metrics are not verified.</div>}
    <div className={`assessment ${assessment.status}`}><Badge status={assessment.status} /><h2>{assessment.label}</h2><p>{assessment.summary}</p></div>
    <div className="section-heading"><h2>Three signals. A clearer decision.</h2><span>Evidence, not a score</span></div>
    <div className="metrics">
      <Card title="Maintenance Activity" status={m.maintenance.status}>
        <p className="value">{m.maintenance.value === null ? 'Unknown' : `${m.maintenance.value} commits`}</p>
        <p className="detail">Last {meta.window_days} days · default branch</p><p>{m.maintenance.message}</p>
        {meta.commits_complete === false && <p className="footnote">Lower bound: only the first 100 commits were retrieved.</p>}
      </Card>
      <Card title="Release Freshness" status={m.release.status}>
        <p className="value">{m.release.version ?? (m.release.value ? date(m.release.value) : 'Unknown')}</p>
        {m.release.value && <p className="detail">{date(m.release.value)} · UTC</p>}
        <p className="source">{m.release.source === 'git_tag' ? 'Git tag · estimated freshness' : m.release.source === 'github_release' ? 'GitHub Release · publication date' : 'No reliable release information'}</p>
        {m.release.source === 'git_tag' ? <><p>Estimated from the associated commit’s committer date, not the tag publication date.</p><details><summary>About this estimate</summary><p>{m.release.message}</p></details></> : <p>{m.release.message}</p>}
      </Card>
      <Card title="Repository Status" status={m.archived.status}>
        <p className="value">{m.archived.value === null ? 'Unknown' : m.archived.value ? 'Archived' : 'Not archived'}</p>
        <p>{m.archived.message}</p><p className="footnote">Not archived does not establish active maintenance. Activity is evaluated separately.</p>
      </Card>
    </div>
    <p className="report-footer">Analyzed {date(meta.analyzed_at)} · {meta.cached ? 'Cached result · up to 15 minutes old' : 'Fresh evaluation'} · GitHub public API</p>
    <p className="disclaimer">A healthy assessment means no major signals were detected by these heuristics. It does not guarantee security, suitability, or future maintenance.</p>
  </section>
}
export default function App() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [invalid, setInvalid] = useState(false)
  const [result, setResult] = useState<Evaluation | null>(null)
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])
  async function submit(event?: FormEvent) {
    event?.preventDefault()
    if (active.current) return
    setResult(null)
    if (!validRepository(input.trim())) {
      setInvalid(true); setError('Enter a repository such as django/django or its full HTTPS GitHub URL.'); return
    }
    setInvalid(false); setError(''); setLoading(true)
    const controller = new AbortController()
    active.current = controller
    try {
      const data = await evaluateRepository(input.trim(), controller.signal)
      if (!controller.signal.aborted && active.current === controller) setResult(data)
    } catch (cause) {
      if (!controller.signal.aborted && active.current === controller) setError(cause instanceof Error ? cause.message : 'Something went wrong. Please try again.')
    } finally {
      if (active.current === controller) { active.current = null; setLoading(false) }
    }
  }
  return <><header><div className="brand-mark" aria-hidden="true">↗</div><div><strong>Repository Evaluator</strong><p>Open source. Informed decisions.</p></div><span className="header-note">Maintenance risk, explained</span></header>
    <main><section className="hero"><p className="eyebrow">Before your next dependency</p><h1>Will you regret this dependency <span>in two years?</span></h1><p className="intro">Check maintenance activity, release freshness, and repository status before adopting an open-source dependency.</p>
      <form onSubmit={submit} noValidate><label htmlFor="repository">GitHub repository</label><div className="search-row"><input id="repository" value={input} onChange={e => setInput(e.target.value)} disabled={loading} placeholder="owner/repository or GitHub URL" autoCapitalize="none" autoCorrect="off" spellCheck={false} aria-invalid={invalid} aria-describedby={invalid ? 'input-hint request-error' : 'input-hint'} /><button disabled={loading} type="submit">{loading ? 'Evaluating…' : 'Evaluate repository'}<span aria-hidden="true"> →</span></button></div><p id="input-hint" className="hint">Use django/django or https://github.com/django/django. Public repositories only.</p></form>
    </section>
    <div className="feedback" aria-live="polite">{loading && <p className="loading" role="status">Evaluating repository… Retrieving maintenance and release information.</p>}</div>
    {error && <div className="error" role="alert"><p id="request-error">{error}</p>{!invalid && <button className="secondary" onClick={() => void submit()}>Try again</button>}</div>}
    {result ? <Results data={result} /> : !loading && !error && <section className="empty"><span className="eyebrow">A focused first check</span><h2>Look beyond the star count.</h2><p>Three explainable signals help you spot maintenance concerns. Enter a repository to see the evidence and its limitations.</p><div className="steps"><span>01 &nbsp; Recent commits</span><span>02 &nbsp; Releases & tags</span><span>03 &nbsp; Archived status</span></div></section>}
    </main><footer>Repository Evaluator <span>Built for thoughtful dependency decisions.</span></footer></>
}
