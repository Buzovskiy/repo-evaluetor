import type { Evaluation } from '../api'
import Badge from './Badge'
import Card from './Card'
interface ResultsProps {
  data: Evaluation
}
function releaseSourceLabel(
  source: Evaluation['metrics']['release']['source'],
) {
  switch (source) {
    case 'git_tag':
      return 'Git tag · estimated freshness'
    case 'github_release':
      return 'GitHub Release · publication date'
    default:
      return 'No reliable release information'
  }
}
function archiveLabel(archived: boolean | null) {
  if (archived === null) return 'Unknown'
  return archived ? 'Archived' : 'Not archived'
}
function formatDate(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Date unavailable'
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeZone: 'UTC',
  }).format(new Date(value))
}
export default function Results({ data }: ResultsProps) {
  const { repository: repo, assessment, metrics, meta } = data
  const github = repo.url?.startsWith('https://github.com/') ? repo.url : null
  return (
    <section aria-label="Evaluation results" className="results">
      <div className="repo-heading">
        <div>
          <p className="eyebrow">Repository report</p>
          <h2>{repo.full_name ?? 'Repository'}</h2>
          {repo.description && <p>{repo.description}</p>}
        </div>
        {github && (
          <a href={github} target="_blank" rel="noreferrer">
            View on GitHub ↗
          </a>
        )}
      </div>
      <div className="repo-meta">
        <span>
          {repo.stars === null
            ? 'Stars unavailable'
            : `☆ ${repo.stars.toLocaleString()} stars`}
        </span>
        <span>Branch: {repo.default_branch ?? 'Unknown'}</span>
      </div>
      {meta.errors.length > 0 && (
        <div className="notice" role="status">
          <strong>Partial results</strong> — Some information could not be
          retrieved from GitHub. Available signals are shown below; unknown
          metrics are not verified.
        </div>
      )}
      <div className={`assessment ${assessment.status}`}>
        <Badge status={assessment.status} />
        <h2>{assessment.label}</h2>
        <p>{assessment.summary}</p>
      </div>
      <div className="section-heading">
        <h2>Three signals. A clearer decision.</h2>
        <span>Evidence, not a score</span>
      </div>
      <div className="metrics">
        <Card title="Maintenance Activity" status={metrics.maintenance.status}>
          <p className="value">
            {metrics.maintenance.value === null
              ? 'Unknown'
              : `${metrics.maintenance.value} commits`}
          </p>
          <p className="detail">
            Last {meta.window_days} days · default branch
          </p>
          <p>{metrics.maintenance.message}</p>
          {meta.commits_complete === false && (
            <p className="footnote">
              Lower bound: only the first 100 commits were retrieved.
            </p>
          )}
        </Card>
        <Card title="Release Freshness" status={metrics.release.status}>
          <p className="value">
            {metrics.release.version ??
              (metrics.release.value
                ? formatDate(metrics.release.value)
                : 'Unknown')}
          </p>
          {metrics.release.value && (
            <p className="detail">{formatDate(metrics.release.value)} · UTC</p>
          )}
          <p className="source">{releaseSourceLabel(metrics.release.source)}</p>
          {metrics.release.source === 'git_tag' ? (
            <>
              <p>
                Estimated from the associated commit’s committer date, not the
                tag publication date.
              </p>
              <details>
                <summary>About this estimate</summary>
                <p>{metrics.release.message}</p>
              </details>
            </>
          ) : (
            <p>{metrics.release.message}</p>
          )}
        </Card>
        <Card title="Repository Status" status={metrics.archived.status}>
          <p className="value">{archiveLabel(metrics.archived.value)}</p>
          <p>{metrics.archived.message}</p>
          <p className="footnote">
            Not archived does not establish active maintenance. Activity is
            evaluated separately.
          </p>
        </Card>
      </div>
      <p className="report-footer">
        Analyzed {formatDate(meta.analyzed_at)} ·{' '}
        {meta.cached
          ? 'Cached result · up to 15 minutes old'
          : 'Fresh evaluation'}{' '}
        · GitHub public API
      </p>
      <p className="disclaimer">
        A healthy assessment means no major signals were detected by these
        heuristics. It does not guarantee security, suitability, or future
        maintenance.
      </p>
    </section>
  )
}
