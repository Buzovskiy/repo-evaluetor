import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { evaluateRepository, validRepository } from './api'
import type { Evaluation } from './api'
import Results from './components/Results'
import './App.css'

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
      setInvalid(true)
      setError(
        'Enter a repository such as django/django or its full HTTPS GitHub URL.',
      )
      return
    }
    setInvalid(false)
    setError('')
    setLoading(true)
    const controller = new AbortController()
    active.current = controller
    try {
      const data = await evaluateRepository(input.trim(), controller.signal)
      if (!controller.signal.aborted && active.current === controller)
        setResult(data)
    } catch (cause) {
      if (!controller.signal.aborted && active.current === controller)
        setError(
          cause instanceof Error
            ? cause.message
            : 'Something went wrong. Please try again.',
        )
    } finally {
      if (active.current === controller) {
        active.current = null
        setLoading(false)
      }
    }
  }
  return (
    <>
      <header>
        <div className="brand-mark" aria-hidden="true">
          ↗
        </div>
        <div>
          <strong>Repository Evaluator</strong>
          <p>Open source. Informed decisions.</p>
        </div>
        <span className="header-note">Maintenance risk, explained</span>
      </header>
      <main>
        <section className="hero">
          <p className="eyebrow">Before your next dependency</p>
          <h1>
            Will you regret this dependency <span>in two years?</span>
          </h1>
          <p className="intro">
            Check maintenance activity, release freshness, and repository status
            before adopting an open-source dependency.
          </p>
          <form onSubmit={submit} noValidate>
            <label htmlFor="repository">GitHub repository</label>
            <div className="search-row">
              <input
                id="repository"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
                placeholder="owner/repository or GitHub URL"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                aria-invalid={invalid}
                aria-describedby={
                  invalid ? 'input-hint request-error' : 'input-hint'
                }
              />
              <button disabled={loading} type="submit">
                {loading ? 'Evaluating…' : 'Evaluate repository'}
                <span aria-hidden="true"> →</span>
              </button>
            </div>
            <p id="input-hint" className="hint">
              Use django/django or https://github.com/django/django. Public
              repositories only.
            </p>
          </form>
        </section>
        <div className="feedback" aria-live="polite">
          {loading && (
            <p className="loading" role="status">
              Evaluating repository… Retrieving maintenance and release
              information.
            </p>
          )}
        </div>
        {error && (
          <div className="error" role="alert">
            <p id="request-error">{error}</p>
            {!invalid && (
              <button className="secondary" onClick={() => void submit()}>
                Try again
              </button>
            )}
          </div>
        )}
        {result && <Results data={result} />}
        {!result && !loading && !error && (
          <section className="empty">
            <span className="eyebrow">A focused first check</span>
            <h2>Look beyond the star count.</h2>
            <p>
              Three explainable signals help you spot maintenance concerns.
              Enter a repository to see the evidence and its limitations.
            </p>
            <div className="steps">
              <span>01 &nbsp; Recent commits</span>
              <span>02 &nbsp; Releases & tags</span>
              <span>03 &nbsp; Archived status</span>
            </div>
          </section>
        )}
      </main>
      <footer>
        Repository Evaluator{' '}
        <span>Built for thoughtful dependency decisions.</span>
      </footer>
    </>
  )
}
