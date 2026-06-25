import { useEffect, useRef, useState } from 'react'
import {
  buildTeamShareUrl,
  getShareTeamName,
  shareTeamUrl,
} from '../../utils/teamShare'

const copiedVisibleMs = 1800

export default function TeamShareButton({ team, className = '', onShareClick = null }) {
  const [copied, setCopied] = useState(false)
  const timeoutRef = useRef(null)
  const shareUrl = buildTeamShareUrl(team)
  const teamName = getShareTeamName(team)

  useEffect(() => () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
  }, [])

  if (!shareUrl) return null

  async function handleShare(event) {
    event.preventDefault()
    event.stopPropagation()

    // Fire share-intent tracking up front — never gated on native-share / copy
    // success, which cannot be reliably interpreted.
    if (typeof onShareClick === 'function') onShareClick()

    const result = await shareTeamUrl(team)
    if (result.status !== 'copied') return

    setCopied(true)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => {
      setCopied(false)
      timeoutRef.current = null
    }, copiedVisibleMs)
  }

  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <button
        type="button"
        onClick={handleShare}
        aria-label={`Share ${teamName} bullpen`}
        data-share-url={shareUrl}
        className="rounded border border-dirt bg-field/60 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus:ring-2 focus:ring-amber/40"
      >
        Share
      </button>
      {copied && (
        <span
          aria-live="polite"
          className="font-mono text-[10px] uppercase tracking-widest text-amber/80"
        >
          Link copied
        </span>
      )}
    </span>
  )
}
