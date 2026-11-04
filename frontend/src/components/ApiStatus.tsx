import { useQuery } from '@tanstack/react-query'
import { RefreshCw, Server } from 'lucide-react'
import { getHealth } from '../lib/api'

export function ApiStatus() {
  const health = useQuery({
    queryKey: ['api-health'], queryFn: ({ signal }) => getHealth(signal),
    retry: false, refetchInterval: 30000, refetchOnWindowFocus: true,
  })
  const connected = health.isSuccess && !health.isError
  return <div className="api-status" aria-label="Local API connection">
    <div className="api-status-title"><Server size={17} aria-hidden="true" /><strong>Local API</strong>
      <span className={`status-dot ${connected ? 'connected' : ''}`} aria-hidden="true" /></div>
    <p role="status">{health.isPending ? 'Checking connection…' : health.isError ? 'API unavailable' : 'Connected to local backend'}</p>
    <p className="caption">{health.isError ? 'Start the backend on port 8000, then retry.' : connected ? 'Process health only; research integrations are planned.' : 'Waiting for a response from your computer.'}</p>
    <button type="button" className="text-button" onClick={() => void health.refetch()} disabled={health.isFetching}>
      <RefreshCw size={13} aria-hidden="true" className={health.isFetching ? 'spin' : ''} />{health.isFetching ? 'Checking…' : 'Check connection'}
    </button>
  </div>
}
