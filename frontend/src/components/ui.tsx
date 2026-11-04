import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export function ActionLink({ to, children, secondary = false }: {
  to: string; children: ReactNode; secondary?: boolean
}) {
  return <Link className={`button ${secondary ? 'button-secondary' : 'button-primary'}`} to={to}>{children}</Link>
}

export function Badge({ children, tone = 'neutral' }: {
  children: ReactNode; tone?: 'neutral' | 'indigo' | 'success' | 'warning'
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function SectionHeading({ eyebrow, title, children }: {
  eyebrow: string; title: string; children?: ReactNode
}) {
  return <div className="section-heading"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2>{children && <p>{children}</p>}</div>
}
