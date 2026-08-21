const RATIO_CLASSES = {
  '1:1': 'desktop:grid-cols-2',
  '7:5': 'desktop:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]',
}

export default function SectionPair({ label, ratio = '1:1', children, className = '' }) {
  const classes = [
    'mt-section grid min-w-0 gap-section desktop:mt-section-lg desktop:items-start desktop:gap-8 [&>*]:min-w-0 [&>*]:mt-0',
    RATIO_CLASSES[ratio] || RATIO_CLASSES['1:1'],
    className,
  ].filter(Boolean).join(' ')

  return (
    <div className={classes} role={label ? 'group' : undefined} aria-label={label || undefined} data-ratio={ratio} data-testid="team-board-section-pair">
      {children}
    </div>
  )
}
