export type Status = 'healthy' | 'warning' | 'critical' | 'unknown'
type Metric<T, U> = { status: Status; value: T | null; unit: U; message: string }
export interface Evaluation {
  repository: { full_name: string | null; url: string | null; description: string | null; default_branch: string | null; stars: number | null; archived: boolean | null }
  assessment: { status: Status; label: string; summary: string }
  metrics: {
    maintenance: Metric<number | string, 'commits'>
    release: Metric<string, 'date'> & { source: 'github_release' | 'git_tag' | null; version: string | null }
    archived: Metric<boolean, 'boolean'>
  }
  meta: { analyzed_at: string; window_days: number; commits_complete: boolean | null; cached: boolean; errors: { endpoint: string; type: string; status: number | null; rate_limit_headers: Record<string, string> }[] }
}
export interface ApiError { error: { code: string; message: string; retry_after_seconds: number | null } }
const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null
const text = (v: unknown) => typeof v === 'string'
const nullableText = (v: unknown) => v === null || text(v)
const number = (v: unknown) => typeof v === 'number' && Number.isFinite(v)
const bool = (v: unknown) => v === null || typeof v === 'boolean'
const status = (v: unknown) => ['healthy', 'warning', 'critical', 'unknown'].includes(String(v))
export function isEvaluation(v: unknown): v is Evaluation {
  if (!object(v) || !object(v.repository) || !object(v.assessment) || !object(v.metrics) || !object(v.meta)) return false
  const { repository: r, assessment: a, metrics: m, meta } = v
  if (!['full_name', 'url', 'description', 'default_branch'].every(k => nullableText(r[k])) || !(r.stars === null || number(r.stars)) || !bool(r.archived)) return false
  if (!status(a.status) || !text(a.label) || !text(a.summary)) return false
  for (const [key, unit] of [['maintenance', 'commits'], ['release', 'date'], ['archived', 'boolean']]) {
    const item = m[key]
    if (!object(item) || !status(item.status) || !text(item.message) || item.unit !== unit) return false
  }
  const maintenance = m.maintenance as Record<string, unknown>
  const release = m.release as Record<string, unknown>
  const archived = m.archived as Record<string, unknown>
  return (maintenance.value === null || text(maintenance.value) || number(maintenance.value))
    && nullableText(release.value) && nullableText(release.version)
    && [null, 'github_release', 'git_tag'].includes(release.source as string | null) && bool(archived.value)
    && text(meta.analyzed_at) && number(meta.window_days) && bool(meta.commits_complete) && typeof meta.cached === 'boolean'
    && Array.isArray(meta.errors) && meta.errors.every(e => object(e) && text(e.endpoint) && text(e.type)
      && (e.status === null || number(e.status)) && object(e.rate_limit_headers) && Object.values(e.rate_limit_headers).every(text))
}
export function validRepository(input: string): boolean {
  let value = input
  if (value.startsWith('https://')) {
    try {
      const url = new URL(value)
      if (url.host !== 'github.com' || url.username || url.password || value.includes('?') || value.includes('#')) return false
      value = url.pathname.slice(1).replace(/\/$/, '').replace(/\.git$/, '')
    } catch { return false }
  }
  const [owner, repo, extra] = value.split('/')
  return !extra && value.split('/').length === 2 && owner.length <= 39
    && /^[a-z\d]+(?:-[a-z\d]+)*$/i.test(owner)
    && /^[a-z\d_.-]{1,100}$/i.test(repo) && !['.', '..'].includes(repo)
}
export async function evaluateRepository(repo: string, signal: AbortSignal): Promise<Evaluation> {
  const base = import.meta.env.VITE_API_BASE_URL
  if (!base) throw new Error('The API address is not configured. Set VITE_API_BASE_URL and rebuild the frontend.')
  let url: URL
  try {
    url = new URL(base)
    url.pathname = url.pathname.replace(/\/+$/, '') + '/api/evaluate/'
    url.search = new URLSearchParams({ repo }).toString()
  } catch { throw new Error('The configured API address is invalid.') }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash) throw new Error('The configured API address is invalid.')
  let response: Response
  try { response = await fetch(url, { signal, credentials: 'omit', headers: { Accept: 'application/json' } }) }
  catch (error) {
    if (signal.aborted) throw error
    throw new Error('Could not connect to the evaluation service. Check your connection and try again.', { cause: error })
  }
  let body: unknown
  try { body = await response.json() }
  catch { throw new Error('The service returned an unexpected response. Please try again.') }
  if (!response.ok) {
    if (object(body) && object(body.error) && text(body.error.message)) {
      const retry = body.error.retry_after_seconds
      throw new Error(body.error.message + (response.status === 429 && number(retry) && Number(retry) >= 0 ? ` Try again in ${retry} seconds.` : ''))
    }
    throw new Error(`The evaluation service could not complete the request (HTTP ${response.status}). Please try again.`)
  }
  if (!isEvaluation(body)) throw new Error('The service returned incomplete or malformed data. Please try again.')
  return body
}
