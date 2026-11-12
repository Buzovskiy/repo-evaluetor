import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
import type { Evaluation } from './api'

const fixture = (): Evaluation => ({
  repository: { full_name: 'a/b', url: 'https://github.com/a/b', description: 'A library', default_branch: 'main', stars: 10, archived: false },
  assessment: { status: 'healthy', label: 'No major signals detected', summary: 'No major signals.' },
  metrics: {
    maintenance: { status: 'healthy', value: '100+', unit: 'commits', message: 'Recent work.' },
    release: { status: 'healthy', value: '2026-01-01T00:00:00Z', unit: 'date', message: 'Release evidence.', source: 'github_release', version: 'v1.2' },
    archived: { status: 'healthy', value: false, unit: 'boolean', message: 'Not archived.' },
  },
  meta: { analyzed_at: '2026-01-02T00:00:00Z', window_days: 90, commits_complete: false, cached: false, errors: [] },
})
const fetchMock = vi.fn()
beforeEach(() => { vi.stubEnv('VITE_API_BASE_URL', 'https://backend.example/'); vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset() })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })
function submit(value = 'a/b') {
  fireEvent.change(screen.getByLabelText('GitHub repository'), { target: { value } })
  fireEvent.click(screen.getByRole('button', { name: /Evaluate repository/ }))
}
function respond(data = fixture()) { fetchMock.mockResolvedValue({ ok: true, json: async () => data }) }

test('initial form and invalid input do not request', () => {
  render(<App />)
  expect(screen.getByText('Look beyond the star count.')).toBeTruthy()
  submit('bad')
  expect(screen.getByRole('alert').textContent).toContain('Enter a repository')
  expect(fetchMock).not.toHaveBeenCalled()
})
test('success renders three metrics, lower bound, release source, and encoded URL', async () => {
  respond(); render(<App />); submit()
  expect(await screen.findByText('100+ commits')).toBeTruthy()
  expect(screen.getAllByRole('article')).toHaveLength(3)
  expect(screen.getByText(/Lower bound/)).toBeTruthy()
  expect(screen.getByText('GitHub Release · publication date')).toBeTruthy()
  expect(String(fetchMock.mock.calls[0][0])).toBe('https://backend.example/api/evaluate/?repo=a%2Fb')
})
test('tag proxy and partial results', async () => {
  const data = fixture(); data.metrics.release.source = 'git_tag'
  data.meta.errors = [{ endpoint: 'commits', type: 'GitHubTimeout', status: null, rate_limit_headers: {} }]
  respond(data); render(<App />); submit()
  expect(await screen.findByText('Partial results')).toBeTruthy()
  expect(screen.getByText(/not the tag publication date/)).toBeTruthy()
})
test('unknown metrics do not invent values', async () => {
  const data = fixture()
  data.metrics.release = { status: 'unknown', value: null, source: null, version: null, unit: 'date', message: 'No date.' }
  data.metrics.archived.value = null; respond(data); render(<App />); submit()
  expect(await screen.findByText('No reliable release information')).toBeTruthy()
  expect(screen.getAllByText('Unknown').length).toBeGreaterThan(1)
})
test.each([[404, 'GitHub repository was not found.', null], [429, 'GitHub rate limit exceeded.', 60], [502, 'GitHub failed.', null], [504, 'GitHub request timed out.', null]])('HTTP %s errors', async (status, message, retry) => {
  fetchMock.mockResolvedValue({ ok: false, status, json: async () => ({ error: { code: 'ERROR', message, retry_after_seconds: retry } }) })
  render(<App />); submit()
  expect((await screen.findByRole('alert')).textContent).toContain(message)
  if (retry) expect(screen.getByRole('alert').textContent).toContain('60 seconds')
  expect(fetchMock).toHaveBeenCalledTimes(1)
})
test('network failure can be retried', async () => {
  fetchMock.mockRejectedValue(new TypeError('offline')); render(<App />); submit()
  expect((await screen.findByRole('alert')).textContent).toContain('Could not connect')
  respond(); fireEvent.click(screen.getByText('Try again'))
  expect(await screen.findByText('100+ commits')).toBeTruthy()
})
test('malformed successful data is rejected', async () => {
  fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) })
  render(<App />); submit()
  expect((await screen.findByRole('alert')).textContent).toContain('malformed')
})
test('pending request blocks duplicates and is aborted on unmount', async () => {
  fetchMock.mockReturnValue(new Promise(() => {}))
  const view = render(<App />); submit()
  fireEvent.submit(screen.getByLabelText('GitHub repository').closest('form')!)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('status').textContent).toContain('Evaluating')
  view.unmount()
  expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true)
})
test('new submission clears prior report until completed', async () => {
  respond(); render(<App />); submit(); await screen.findByText('100+ commits')
  fetchMock.mockReturnValue(new Promise(() => {})); submit('c/d')
  await waitFor(() => expect(screen.queryByText('100+ commits')).toBeNull())
})
