import { useState } from 'react'

// Shared story presentation pieces for the Stories feed: section heading,
// labeled blueprint sections, flat narrative fallback, and the disclosure
// note. Presentation only — everything renders backend-authored copy and
// invents nothing.

export function SectionHeading({ title, subtitle, right }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2 border-b border-dirt pb-2">
      <div>
        <h2 className="font-display text-2xl tracking-wider text-chalk100 uppercase">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-chalk400">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function storyParagraphs(value) {
  return cleanText(value)
    .split(/\n{2,}/)
    .map(paragraph => paragraph.trim())
    .filter(Boolean)
}

const CONTEXT_STORY_KINDS = new Set([
  'team_pressure',
  'team_workload',
  'team_workload_continuity',
  'team_recovery',
])

const COMPACT_CONTEXT_STORY_KINDS = new Set([
  'team_workload_continuity',
])

const MEANINGFUL_CONTEXT_TYPES = new Set([
  'rotation_length',
  'usage_demand',
])

function storyHasTeam(story = {}) {
  return story.teamId != null || story.team?.teamId != null || Boolean(story.teamName || story.team?.teamName)
}

function storyContextHasMeaningfulSignal(story = {}) {
  const type = cleanText(story.context?.type || story.contextType).toLowerCase()
  if (!type) return false
  if (!MEANINGFUL_CONTEXT_TYPES.has(type)) return false

  const trend = cleanText(story.context?.evidence?.trend || story.context?.trend).toLowerCase()
  return !['insufficient_data', 'unclear', 'stable', 'flat'].includes(trend)
}

export function shouldRenderStoryContext(story = {}, options = {}) {
  if (!cleanText(story.context_note)) return false
  if (!storyHasTeam(story)) return false

  const kind = cleanText(story.storyKind || story.family || story.kicker).toLowerCase()
  // Fallback stays conservative until every future story source carries a
  // reliable family/type. Context is supporting explanation, not a reason to
  // make generic or league-wide cards longer.
  if (!CONTEXT_STORY_KINDS.has(kind)) return false

  if (options.compact) {
    return (
      COMPACT_CONTEXT_STORY_KINDS.has(kind)
      && Boolean(cleanText(story.continuity_note))
      && storyContextHasMeaningfulSignal(story)
    )
  }

  return true
}

export function StorySection({
  label,
  text,
  children,
  compact = false,
  tone = 'observation',
  bodyClassName = '',
  className = '',
}) {
  const body = children ?? cleanText(text)
  if (body == null || body === '') return null

  const bodyClass = {
    observation: compact ? 'text-chalk400' : 'text-chalk300',
    continuity: 'text-chalk400/85',
    context: 'text-chalk400/65',
  }[tone] || 'text-chalk400'
  const bodySize = tone === 'observation'
    ? (compact ? 'text-xs' : 'text-sm')
    : 'text-[11px]'

  return (
    <section
      className={`space-y-0.5 ${className}`}
    >
      {typeof body === 'string' ? (
        <p className={`${bodySize} leading-relaxed ${bodyClass} ${bodyClassName}`}>{body}</p>
      ) : body}
    </section>
  )
}

// V2 Story Blueprint (Phase A): render the backend's labeled teaching sections
// (what everyone saw / what BaseballOS noticed / evidence / why it matters / why
// it matters tomorrow). Presentation only — it renders backend-authored copy and
// invents nothing. Returns null when no usable sections are supplied, so callers
// fall back to the existing flat narrative.
// Sections shown when a collapsible blueprint is collapsed: the hook (what
// everyone saw) and the insight (what BaseballOS noticed). Evidence / why it
// matters / why it matters tomorrow stay behind "Read the full read".
const COLLAPSED_BLUEPRINT_KEYS = new Set(['what_everyone_saw', 'what_baseballos_noticed'])

export function StoryBlueprint({
  sections,
  compact = false,
  collapsible = false,
  initialExpanded = false,
  onExpand = null,
  className = '',
  bodyClassName = '',
}) {
  const [expanded, setExpanded] = useState(initialExpanded)

  const usable = (Array.isArray(sections) ? sections : [])
    .map(section => ({
      key: cleanText(section?.key),
      label: cleanText(section?.label),
      paragraphs: storyParagraphs(section?.text),
    }))
    .filter(section => section.label && section.paragraphs.length)

  if (!usable.length) return null

  // Collapsed shows the lead-in (what everyone saw + what BaseballOS noticed);
  // the rest stays behind the toggle. Falls back to the first two sections if the
  // backend ever sends unrecognized keys, so collapse never empties the card.
  const lead = usable.filter(section => COLLAPSED_BLUEPRINT_KEYS.has(section.key))
  const collapsedSections = lead.length ? lead : usable.slice(0, 2)
  const canCollapse = collapsible && collapsedSections.length < usable.length
  const visible = canCollapse && !expanded ? collapsedSections : usable

  const handleToggle = (event) => {
    event.preventDefault()
    event.stopPropagation()
    const next = !expanded
    setExpanded(next)
    // story_viewed fires on the expand transition only — never on collapse.
    if (next && typeof onExpand === 'function') onExpand()
  }

  return (
    <div className={`story-blueprint ${className}`}>
      {visible.map((section, index) => (
        <section key={section.key || `blueprint-${index}`} className={index > 0 ? 'mt-3' : ''}>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            {section.label}
          </div>
          {section.paragraphs.map((paragraph, paraIndex) => (
            <p
              key={`${section.key}-${paraIndex}`}
              className={`mt-1 ${compact ? 'text-xs' : 'text-sm'} leading-relaxed text-chalk300 ${bodyClassName}`}
            >
              {paragraph}
            </p>
          ))}
        </section>
      ))}
      {canCollapse && (
        <button
          type="button"
          onClick={handleToggle}
          aria-expanded={expanded}
          className="story-blueprint-toggle mt-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-amber/80 transition-colors hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/40"
        >
          {expanded ? 'Show less' : 'Read the full read'}
          <span aria-hidden="true">{expanded ? '↑' : '↓'}</span>
        </button>
      )}
    </div>
  )
}

export function StoryPresentation({
  story,
  observation,
  compact = false,
  className = '',
  observationBodyClassName = '',
  forceContext = false,
}) {
  const blueprintSections = Array.isArray(story?.blueprint) ? story.blueprint : []
  const hasBlueprint = blueprintSections.length > 0
  const narrativeText = cleanText(story?.narrative || story?.story_body || observation || story?.body || story?.observation)
  const hasContinuity = Boolean(cleanText(story?.continuity_note))
  const hasContext = forceContext
    ? Boolean(cleanText(story?.context_note))
    : shouldRenderStoryContext(story, { compact })
  const baseParagraphs = storyParagraphs(narrativeText)

  return (
    <div className={`story-presentation ${className}`}>
      {hasBlueprint ? (
        <StoryBlueprint
          sections={blueprintSections}
          compact={compact}
          bodyClassName={observationBodyClassName}
        />
      ) : baseParagraphs.map((paragraph, index) => (
        <StorySection
          key={`story-paragraph-${index}`}
          text={paragraph}
          compact={compact}
          tone="observation"
          bodyClassName={observationBodyClassName}
          className={index > 0 ? 'mt-2' : ''}
        />
      ))}
      {hasContinuity && (
        <StorySection
          text={story.continuity_note}
          compact
          tone="continuity"
          className="mt-2 border-l border-dirt/60 pl-2"
        />
      )}
      {hasContext && (
        <StorySection
          text={story.context_note}
          compact
          tone="context"
          className="mt-1.5 border-l border-dirt/40 pl-2"
        />
      )}
    </div>
  )
}

export function StoryDisclosureNote({ note, className = '' }) {
  const text = cleanText(note)
  if (!text) return null
  return (
    <p className={`mt-3 border-t border-dirt/60 pt-2 text-[11px] leading-relaxed text-chalk600 ${className}`}>
      {text}
    </p>
  )
}
