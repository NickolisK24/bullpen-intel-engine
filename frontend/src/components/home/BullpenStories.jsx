import { Link } from 'react-router-dom'
import { homeTone } from './homePresentationView'

// Section 2 — Three Things To Watch. The briefing cut: only the few signals
// that matter most this morning, in plain baseball language — what the
// workload data shows, never what anyone should do about it. The full feed
// lives on the Stories page.
export const SHORT_LIST_LIMIT = 3

export default function BullpenStories({ stories, showCta = true }) {
  const shortList = (Array.isArray(stories?.items) ? stories.items : []).slice(0, SHORT_LIST_LIMIT)

  return (
    <section className="mb-8" aria-label="Three things to watch">
      <SectionHeading
        title="Three Things To Watch"
        subtitle="The briefing-level signals behind the flagship observation."
      />

      {!stories?.hasStories ? (
        <div className="card p-5 text-sm text-chalk400">{stories?.fallback}</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {shortList.map((story, index) => (
            <StoryCard key={`${story.kicker}-${index}`} story={story} />
          ))}
        </div>
      )}

      {showCta && (
        <div className="mt-3 text-right">
          <Link
            to="/stories"
            className="inline-flex items-center rounded border border-dirt bg-dugout px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-chalk200 transition-colors hover:border-amber/40 hover:text-amber"
          >
            Open Stories for more observations →
          </Link>
        </div>
      )}
    </section>
  )
}

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
export function StoryBlueprint({
  sections,
  compact = false,
  className = '',
  bodyClassName = '',
}) {
  const usable = (Array.isArray(sections) ? sections : [])
    .map(section => ({
      key: cleanText(section?.key),
      label: cleanText(section?.label),
      paragraphs: storyParagraphs(section?.text),
    }))
    .filter(section => section.label && section.paragraphs.length)

  if (!usable.length) return null

  return (
    <div className={`story-blueprint ${className}`}>
      {usable.map((section, index) => (
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

// A story card is a doorway: team stories step into that club's bullpen
// board, league notes open the league view, data notes open Data & Trust.
// A story with no meaningful destination renders as plain copy — no CTA, no
// pretend link.
function StoryCard({ story }) {
  const tone = homeTone(story.tone)
  const hasDestination = Boolean(story.href)

  const inner = (
    <>
      <span className="h-1 w-8 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />

      <h3 className="mt-3 font-display text-xl leading-tight tracking-wide text-chalk100 group-hover:text-amber transition-colors">
        {story.title}
      </h3>

      <StoryPresentation story={story} compact className="mt-2 flex-1" />
      <StoryDisclosureNote note={story.disclosureNote || story.disclosure_note} />

      {hasDestination && (
        <div className="mt-3 font-mono text-[10px] uppercase tracking-widest text-chalk600 group-hover:text-amber transition-colors">
          {story.cta || 'Open the full picture'} →
        </div>
      )}
    </>
  )

  if (!hasDestination) {
    return <article className="card flex flex-col p-4">{inner}</article>
  }

  return (
    <Link
      to={story.href}
      className="card group flex flex-col p-4 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5"
    >
      {inner}
    </Link>
  )
}
