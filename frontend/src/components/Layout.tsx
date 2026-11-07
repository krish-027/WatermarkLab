import { useEffect, useRef, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { ArrowUpRight, AudioLines, Menu, X } from 'lucide-react'
import { AccountNavigation } from './AccountNavigation'

const navigation = [
  ['Home', '/'], ['About', '/#about'], ['How It Works', '/#how-it-works'],
  ['Research Methods', '/#research-methods'], ['Documentation', '/documentation'],
] as const

export function Brand() {
  return <Link to="/" className="brand" aria-label="WatermarkLab home"><span className="brand-symbol"><AudioLines size={23} aria-hidden="true" /></span><span>Watermark<span className="brand-light">Lab</span></span></Link>
}

export function Layout() {
  const [open, setOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const location = useLocation()
  useEffect(() => {
    setOpen(false)
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView?.()
    else window.scrollTo?.(0, 0)
  }, [location])
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); menuButton.current?.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="site-header"><div className="container header-inner"><Brand />
      <nav className="desktop-nav" aria-label="Main navigation">{navigation.map(([label, to]) => <Link key={label} to={to}>{label}</Link>)}</nav>
      <div className="header-account"><AccountNavigation /></div>
      <div className="header-actions"><Link className="button button-primary button-small" to="/explore">Get Started <ArrowUpRight size={15} aria-hidden="true" /></Link></div>
      <button ref={menuButton} type="button" className="menu-button" aria-label={open ? 'Close navigation' : 'Open navigation'} aria-expanded={open} aria-controls="mobile-navigation" onClick={() => setOpen(!open)}>{open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}</button>
    </div>
    {open && <nav id="mobile-navigation" className="mobile-nav" aria-label="Mobile navigation">{navigation.map(([label, to]) => <Link onClick={() => setOpen(false)} key={label} to={to}>{label}</Link>)}<Link to="/explore">Get Started</Link></nav>}
    </header>
    <main id="main" tabIndex={-1}><Outlet /></main>
    <footer className="site-footer"><div className="container footer-top"><div><Brand /><p>Explore. Detect. Evaluate.</p><p className="caption">A local research project in text provenance.</p></div><div className="footer-links"><Link to="/#about">About the project</Link><Link to="/documentation#methodology">Methodology</Link><Link to="/documentation">Documentation</Link><Link to="/documentation#references">Research references</Link><Link to="/documentation#project">Project & contributors</Link><Link to="/documentation#privacy">Privacy & limitations</Link></div></div><div className="container footer-bottom"><span>WatermarkLab · AI Text Watermark Detection & Robustness Analysis</span><span>Built for careful, reproducible research.</span></div></footer>
  </>
}
