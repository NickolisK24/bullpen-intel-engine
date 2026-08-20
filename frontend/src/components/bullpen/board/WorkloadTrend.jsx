import { useId, useState } from 'react'
import { formatDateOnly } from '../../../utils/dateDisplay'

function initialPublishedSlot(slots) {
  for (let index = slots.length - 1; index >= 0; index -= 1) {
    if (slots[index].published) return slots[index]
  }
  return null
}

function barHeight(outs, maximum) {
  if (outs === 0) return '2px'
  return `${Math.max(8, (outs / maximum) * 100)}%`
}

function slotValueText(slot) {
  const date = formatDateOnly(slot.date, { month: 'short' })
  return slot.published ? `${date}: ${slot.outs} outs` : `${date}: unavailable`
}

export function chartKeyIndex(key, currentIndex, lastIndex) {
  if (key === 'Home') return 0
  if (key === 'End') return lastIndex
  if (key === 'ArrowLeft' || key === 'ArrowDown') return Math.max(0, currentIndex - 1)
  if (key === 'ArrowRight' || key === 'ArrowUp') return Math.min(lastIndex, currentIndex + 1)
  return null
}

export function chartPointerIndex(clientX, left, width, lastIndex) {
  if (!Number.isFinite(clientX) || !Number.isFinite(left) || !Number.isFinite(width) || width <= 0) return null
  const position = Math.min(1, Math.max(0, (clientX - left) / width))
  return Math.round(position * lastIndex)
}

export default function WorkloadTrend({ view }) {
  const slots = view?.available ? view.slots : []
  const [selectedDate, setSelectedDate] = useState(() => initialPublishedSlot(slots)?.date || null)
  const instructionsId = useId()
  if (!view?.available || slots.length === 0) return null

  const selected = slots.find(slot => slot.date === selectedDate) || initialPublishedSlot(slots) || slots[0]
  const selectedIndex = Math.max(0, slots.findIndex(slot => slot.date === selected.date))
  const maximum = Math.max(1, ...slots.filter(slot => slot.published).map(slot => slot.outs))
  const labelIndexes = [0, Math.floor((slots.length - 1) / 2), slots.length - 1]
  const selectPointerDate = event => {
    const rect = event.currentTarget.getBoundingClientRect()
    const nextIndex = chartPointerIndex(event.clientX, rect.left, rect.width, slots.length - 1)
    if (nextIndex != null) setSelectedDate(slots[nextIndex].date)
  }

  return (
    <figure className="mt-section" data-testid="workload-trend">
      <figcaption>
        <h3 className="type-overline">Daily relief workload</h3>
        <p id={instructionsId} className="type-compact mt-meta">
          Published outs across 30 calendar days. Open slots are unavailable. Swipe or use the arrow keys to inspect each day.
        </p>
      </figcaption>
      <div className="mt-row min-h-11" role="status" aria-live="polite" data-testid="workload-trend-readout">
        {selected && (
          <p className="type-compact">
            <span className="text-text-primary">{formatDateOnly(selected.date, { month: 'short' })}</span>
            {' · '}
            <span className="tabular-nums text-text-primary">
              {selected.published ? `${selected.outs} outs` : 'Unavailable'}
            </span>
          </p>
        )}
      </div>
      <div
        className="relative grid h-24 items-end gap-[2px] overflow-hidden border-b border-line-default focus-within:ring-2 focus-within:ring-line-focus focus-within:ring-offset-2 focus-within:ring-offset-surface-base tablet:h-32 lg:h-36 desktop:h-40"
        style={{ gridTemplateColumns: `repeat(${slots.length}, minmax(0, 1fr))` }}
      >
        <input
          type="range"
          min="0"
          max={slots.length - 1}
          step="1"
          value={selectedIndex}
          aria-label="Inspect daily bullpen relief workload"
          aria-describedby={instructionsId}
          aria-valuetext={slotValueText(selected)}
          onChange={event => setSelectedDate(slots[Number(event.target.value)].date)}
          onPointerDown={selectPointerDate}
          onPointerMove={event => {
            if (event.buttons !== 0) selectPointerDate(event)
          }}
          onKeyDown={event => {
            const nextIndex = chartKeyIndex(event.key, selectedIndex, slots.length - 1)
            if (nextIndex == null) return
            event.preventDefault()
            setSelectedDate(slots[nextIndex].date)
          }}
          className="absolute inset-0 z-10 h-full w-full cursor-crosshair opacity-0"
          data-testid="workload-trend-control"
        />
        {slots.map(slot => slot.published ? (
          <span
            key={slot.date}
            className="block min-w-0 bg-text-secondary"
            style={{ height: barHeight(slot.outs, maximum) }}
            aria-hidden="true"
            data-published="true"
            data-outs={slot.outs}
          />
        ) : (
          <span
            key={slot.date}
            className="block h-2 min-w-0 border-t border-text-withheld"
            aria-hidden="true"
            data-published="false"
          />
        ))}
      </div>
      <div className="mt-meta flex min-w-0 justify-between gap-meta type-overline" aria-hidden="true">
        {labelIndexes.map((index, labelIndex) => (
          <span
            key={slots[index].date}
            className={`min-w-0 whitespace-nowrap ${labelIndex === 1 ? 'hidden sm:inline' : ''}`}
          >
            {formatDateOnly(slots[index].date, { month: 'short' })?.replace(', ', ' ')}
          </span>
        ))}
      </div>
    </figure>
  )
}
