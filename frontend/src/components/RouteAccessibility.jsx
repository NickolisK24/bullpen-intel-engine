import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

export default function RouteAccessibility() {
  const location = useLocation()
  const previousPath = useRef(location.pathname)
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    if (previousPath.current === location.pathname) return
    previousPath.current = location.pathname

    const frame = window.requestAnimationFrame(() => {
      const main = document.getElementById('main-content')
      const heading = main?.querySelector('h1')
      if (!main) return

      // The route main remains mounted while an async route heading can be
      // replaced by its loaded state. Keep focus on that stable destination.
      if (!main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1')
      main.focus({ preventScroll: false })
      setAnnouncement(heading?.textContent?.trim() || 'Page loaded')
    })

    return () => window.cancelAnimationFrame(frame)
  }, [location.pathname])

  return (
    <div className="sr-only" aria-live="polite" aria-atomic="true">
      {announcement}
    </div>
  )
}
