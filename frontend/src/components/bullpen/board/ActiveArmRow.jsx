import { SkeletonBlock } from '../../UI/Skeleton'

const markerClass = {
  dot: 'active-arm-read__marker--dot',
  square: 'active-arm-read__marker--square',
  ring: 'active-arm-read__marker--ring',
}

function displayValue(value) {
  return value == null ? '—' : value
}

function ArmRead({ label, tone = 'withheld', marker = 'ring' }) {
  return (
    <span className={`active-arm-read active-arm-read--${tone}`}>
      <span className={`active-arm-read__marker ${markerClass[marker] || markerClass.ring}`} aria-hidden="true" />
      <span className="font-medium">{label || '—'}</span>
    </span>
  )
}

function TableCell({ value, className = '' }) {
  return (
    <span className={`active-arm-row__cell type-data ${value == null ? 'text-text-withheld' : 'text-text-secondary'} ${className}`.trim()}>
      {displayValue(value)}
    </span>
  )
}

export function ActiveArmRowSkeleton() {
  return (
    <div className="active-arm-row active-arm-row--skeleton" role="status" aria-label="Loading reliever record" aria-busy="true">
      <div>
        <SkeletonBlock className="h-5 w-40 max-w-full" />
        <SkeletonBlock className="mt-meta h-3 w-24 max-w-full" />
      </div>
      <SkeletonBlock className="h-5 w-24 max-w-full" />
      <SkeletonBlock className="h-4 w-full max-w-48" />
    </div>
  )
}

export default function ActiveArmRow({
  pitcherId,
  name,
  roleLabel,
  roleWithheld = false,
  readLabel,
  readTone = 'withheld',
  readMarker = 'ring',
  daysSince,
  lastGamePitches,
  appearancesLast7,
  pitchesLast7,
  pattern,
  showLastGamePitches = false,
  href,
  onAction,
  actionAriaLabel,
  partialMessage,
  loading = false,
}) {
  if (loading) return <ActiveArmRowSkeleton />

  const rowClassName = `active-arm-row ${showLastGamePitches ? 'active-arm-row--with-last-p' : ''}`
  const content = (
    <>
      <span className="active-arm-row__identity min-w-0">
        <span className="active-arm-row__name font-board text-base font-semibold leading-tight text-text-primary tablet:text-[0.9375rem]">
          {name || 'Reliever'}
        </span>
        <span className={`type-metadata active-arm-row__role mt-meta ${roleWithheld || !roleLabel ? 'text-text-withheld' : 'text-text-tertiary'}`}>
          {roleLabel || '—'}
        </span>
        {pattern && <span className="type-metadata active-arm-row__tablet-pattern mt-meta font-medium text-state-caution">{pattern}</span>}
      </span>

      <span className="active-arm-row__read min-w-0">
        <ArmRead label={readLabel} tone={readTone} marker={readMarker} />
      </span>

      <span className="active-arm-row__mobile-meta type-metadata min-w-0 border-t border-line-subtle/70 pt-meta">
        <span className={daysSince == null ? 'text-text-withheld' : 'text-text-secondary'}>{daysSince == null ? '— rest' : `${daysSince}d rest`}</span>
        <span aria-hidden="true"> · </span>
        <span className={appearancesLast7 == null ? 'text-text-withheld' : ''}>{displayValue(appearancesLast7)} app</span>
        <span> / </span>
        <span className={pitchesLast7 == null ? 'text-text-withheld' : ''}>{displayValue(pitchesLast7)} p (7d)</span>
        {lastGamePitches != null && <><span aria-hidden="true"> · </span><span>{lastGamePitches} last P</span></>}
        {pattern && <><span aria-hidden="true"> · </span><span className="font-medium text-state-caution">{pattern}</span></>}
      </span>

      <TableCell value={daysSince == null ? null : `${daysSince}d`} className="active-arm-row__rest" />
      {showLastGamePitches && <TableCell value={lastGamePitches} className="active-arm-row__last-p" />}
      <TableCell value={appearancesLast7} className="active-arm-row__app" />
      <TableCell value={pitchesLast7} className="active-arm-row__pitches" />
      <TableCell value={pattern} className="active-arm-row__pattern" />
      <span className="active-arm-row__destination type-metadata font-medium">Open</span>

      {partialMessage && (
        <span className="active-arm-row__partial type-metadata text-text-withheld" role="status">
          {partialMessage}
        </span>
      )}
    </>
  )

  if (typeof onAction === 'function') {
    return (
      <button
        type="button"
        onClick={onAction}
        onKeyDown={event => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          onAction(event)
        }}
        className={rowClassName}
        aria-label={actionAriaLabel || `Open pitcher context for ${name || 'reliever'}`}
        data-pitcher-id={pitcherId ?? undefined}
      >
        {content}
      </button>
    )
  }

  if (href) {
    return (
      <a
        href={href}
        className={rowClassName}
        aria-label={actionAriaLabel || `Open pitcher context for ${name || 'reliever'}`}
        data-pitcher-id={pitcherId ?? undefined}
      >
        {content}
      </a>
    )
  }

  return <article className={rowClassName} aria-label={`${name || 'Reliever'} record`}>{content}</article>
}
