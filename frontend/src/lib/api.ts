export interface Health {
  status: 'ok'
  service: 'watermarklab-api'
  version: string
}

export function apiBaseUrl(): string {
  const url = new URL(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Invalid API URL configuration')
  }
  return url.href.replace(/\/$/, '')
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const timeout = AbortSignal.timeout(5000)
  const response = await fetch(`${apiBaseUrl()}/health`, {
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: { Accept: 'application/json' },
    credentials: 'omit',
  })
  if (!response.ok) throw new Error('API health request failed')
  const body: unknown = await response.json()
  if (!body || typeof body !== 'object' || !('status' in body) || body.status !== 'ok'
    || !('service' in body) || body.service !== 'watermarklab-api'
    || !('version' in body) || typeof body.version !== 'string') {
    throw new Error('Unexpected API health response')
  }
  return body as Health
}
