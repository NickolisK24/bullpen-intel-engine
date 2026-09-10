import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { normalizeEvidenceSection } from '../utils/evidenceLinks'

const MAX_MUTATION_CHECKS = 50

export default function useEvidenceHashNavigation(view) {
  const location = useLocation()

  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const section = normalizeEvidenceSection(location.hash, view)
    if (!section) return undefined

    const revealTarget = () => {
      const target = document.getElementById(section)
      if (!target) return false
      target.scrollIntoView({ block: 'start' })
      target.focus({ preventScroll: true })
      return true
    }

    if (revealTarget()) return undefined

    let checks = 0
    const observer = new MutationObserver(() => {
      checks += 1
      if (revealTarget() || checks >= MAX_MUTATION_CHECKS) observer.disconnect()
    })
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [location.hash, location.pathname, location.search, view])
}
