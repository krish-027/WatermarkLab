import type { User } from '@supabase/supabase-js'

export type Profile = { id: string; display_name: string }

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim().replace(/\s+/gu, ' ').slice(0, 100) : null
}

export function accountIdentity(user: User, profile: Profile | null = null) {
  const metadata = user.user_metadata || {}
  const name = text(profile?.id === user.id ? profile.display_name : null)
    || text(metadata.display_name) || text(metadata.full_name) || text(metadata.name)
  const email = text(user.email)
  const label = name || email?.split('@')[0] || 'Researcher'
  const words = label.split(' ').filter(Boolean)
  const initials = name || email
    ? (words.length > 1 ? Array.from(words[0])[0] + Array.from(words[words.length - 1])[0] : Array.from(label).slice(0, 2).join('')).toLocaleUpperCase()
    : 'WL'
  return { name, email, label, initials }
}
