import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
function configuredClient() {
  if (!url || !key || !key.startsWith('sb_publishable_')) return null
  try {
    const origin = new URL(url)
    if (origin.protocol !== 'https:' || origin.username || origin.password || origin.search || origin.hash || !['', '/'].includes(origin.pathname)) return null
    return createClient(url, key, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: 'pkce' },
    })
  } catch { return null }
}
export const supabase = configuredClient()
