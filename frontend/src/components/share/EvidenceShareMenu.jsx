import { useEffect, useRef, useState } from 'react'
import {
  copyExactLink,
  downloadEvidenceCard,
  shareEvidenceCard,
  shareExactLink,
} from '../../utils/shareActions'

const CARD_UNAVAILABLE = 'Card unavailable until a current evidence-backed read is available.'

function resultMessage(result) {
  if (result?.status === 'shared_card') return 'Card shared.'
  if (result?.status === 'shared_link') return 'Exact link shared.'
  if (result?.status === 'copied') return 'Exact link copied.'
  if (result?.status === 'downloaded') return 'Card download started.'
  if (result?.status === 'cancelled') return 'Share cancelled.'
  if (result?.status === 'generation_failed') return 'Card could not be generated.'
  return 'Sharing is unavailable right now.'
}

export default function EvidenceShareMenu({
  cardModel = null,
  context,
  destinationUrl,
  shareText,
  linkOnly = false,
  className = '',
}) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const rootRef = useRef(null)
  const busyRef = useRef(false)
  const cardAvailable = Boolean(cardModel)

  useEffect(() => {
    if (!open) return undefined
    function closeOnOutside(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    function closeOnEscape(event) {
      if (event.key === 'Escape') {
        setOpen(false)
        rootRef.current?.querySelector('[data-share-menu-trigger]')?.focus()
      }
    }
    document.addEventListener('pointerdown', closeOnOutside)
    document.addEventListener('focusin', closeOnOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutside)
      document.removeEventListener('focusin', closeOnOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  async function run(action) {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setMessage('')
    try {
      let result
      if (action === 'share') {
        result = linkOnly
          ? await shareExactLink({ destinationUrl, shareText, context })
          : await shareEvidenceCard({ model: cardModel, shareText, context })
      } else if (action === 'copy') {
        result = await copyExactLink({ destinationUrl, context })
      } else {
        result = await downloadEvidenceCard({ model: cardModel, context })
      }
      setMessage(resultMessage(result))
      if (['shared_card', 'shared_link', 'copied', 'downloaded'].includes(result?.status)) {
        setOpen(false)
      }
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  if (!destinationUrl) return null

  return (
    <div ref={rootRef} className={`relative inline-flex ${className}`} data-evidence-share-menu>
      <button
        type="button"
        data-share-menu-trigger
        aria-label="Open evidence sharing options"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
        className="rounded border border-dirt bg-field/60 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus:ring-2 focus:ring-amber/40"
      >
        Share
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Evidence sharing options"
          className="absolute right-0 top-full z-30 mt-2 w-64 rounded border border-dirt bg-dugout p-2 shadow-xl"
        >
          <button
            type="button"
            role="menuitem"
            disabled={busy || (!linkOnly && !cardAvailable)}
            title={!linkOnly && !cardAvailable ? CARD_UNAVAILABLE : undefined}
            onClick={() => run('share')}
            className="block w-full rounded px-3 py-2 text-left text-sm text-chalk200 hover:bg-field disabled:cursor-not-allowed disabled:text-chalk600"
          >
            {linkOnly ? 'Share exact link' : 'Share card'}
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={busy}
            onClick={() => run('copy')}
            className="block w-full rounded px-3 py-2 text-left text-sm text-chalk200 hover:bg-field disabled:cursor-not-allowed disabled:text-chalk600"
          >
            Copy exact link
          </button>
          {!linkOnly && (
            <button
              type="button"
              role="menuitem"
              disabled={busy || !cardAvailable}
              title={!cardAvailable ? CARD_UNAVAILABLE : undefined}
              onClick={() => run('download')}
              className="block w-full rounded px-3 py-2 text-left text-sm text-chalk200 hover:bg-field disabled:cursor-not-allowed disabled:text-chalk600"
            >
              Download card
            </button>
          )}
          {!linkOnly && !cardAvailable && (
            <p className="px-3 py-2 text-xs leading-relaxed text-chalk500">{CARD_UNAVAILABLE}</p>
          )}
        </div>
      )}
      {message && (
        <span className="ml-2 self-center whitespace-nowrap font-mono text-[10px] uppercase tracking-wider text-chalk400" aria-live="polite">
          {message}
        </span>
      )}
    </div>
  )
}
