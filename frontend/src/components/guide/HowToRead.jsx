import { Link } from 'react-router-dom'
import {
  ARM_AVAILABILITY_DEFINITIONS,
  CONCEPT_DEFINITIONS,
  FRESHNESS_LABEL_DEFINITIONS,
  SUPPORTING_CONCEPT_DEFINITIONS,
  TEAM_STATE_DEFINITIONS,
} from '../../utils/bullpenConcepts'
import { PUBLIC_BOUNDARIES } from '../../utils/publicBoundaries'

// Every definition on this page renders from the canonical public dictionary
// (utils/bullpenConcepts.js) and the canonical boundary language
// (utils/publicBoundaries.js) — no hardcoded copies.
const asCard = ({ name, definition }) => ({ title: name, body: definition })

const HERO = {
  eyebrow: 'HOW TO READ',
  title: 'How to Read BaseballOS',
  lead: 'BaseballOS uses plain baseball reads to explain bullpen state.',
  sub: "Every label on the site describes today's context — how much a bullpen is carrying, who's rested, and where the late-inning margin is thin. Here's what each term means, in one line.",
}

const TEAM_STATES = TEAM_STATE_DEFINITIONS.map(asCard)

const ARM_STATES = ARM_AVAILABILITY_DEFINITIONS.map(asCard)

const BULLPEN_READS = [
  CONCEPT_DEFINITIONS.pressure,
  CONCEPT_DEFINITIONS.recovery,
  CONCEPT_DEFINITIONS.concentration,
  CONCEPT_DEFINITIONS.cleanOptions,
  SUPPORTING_CONCEPT_DEFINITIONS.coverageSafety,
  SUPPORTING_CONCEPT_DEFINITIONS.trustedArms,
].map(asCard)

const FRESHNESS_LABELS = FRESHNESS_LABEL_DEFINITIONS.map(asCard)

const USING_READS = [
  PUBLIC_BOUNDARIES.descriptiveScope,
  'It shows how current the data is, explains how each read is built, and clearly states what it cannot see, including manager intent, bullpen phones, and final game-day decisions.',
  PUBLIC_BOUNDARIES.saysSoInsteadOfGuessing,
  'The picture is a starting point for your own read—not a verdict.',
]

function Section({ id, title, intro, children }) {
  return (
    <section id={id} className="card p-5 sm:p-6">
      <h2 className="font-display text-2xl tracking-wider text-chalk100">
        {title}
      </h2>
      {intro && (
        <p className="mt-3 max-w-3xl text-sm leading-7 text-chalk400">
          {intro}
        </p>
      )}
      <div className="mt-5">
        {children}
      </div>
    </section>
  )
}

function DefinitionGrid({ items, columns = 'md:grid-cols-3' }) {
  return (
    <div className={`grid grid-cols-1 gap-4 ${columns}`}>
      {items.map(item => (
        <article key={item.title} className="rounded border border-dirt bg-field/45 p-4">
          <h3 className="font-mono text-xs uppercase tracking-widest text-amber/80">
            {item.title}
          </h3>
          <p className="mt-3 text-sm leading-6 text-chalk400">
            {item.body}
          </p>
        </article>
      ))}
    </div>
  )
}

export default function HowToRead() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-6xl mx-auto space-y-8">
      <section className="rounded border border-dirt bg-dugout/70 p-6 sm:p-8">
        <div className="font-mono text-xs uppercase tracking-widest text-amber/75">
          {HERO.eyebrow}
        </div>
        <h1 className="mt-3 font-display text-4xl tracking-wider text-chalk100 sm:text-5xl">
          {HERO.title}
        </h1>
        <p className="mt-5 max-w-3xl text-xl leading-relaxed text-chalk200">
          {HERO.lead}
        </p>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-chalk400">
          {HERO.sub}
        </p>
      </section>

      <Section
        id="team-state"
        title="Team State"
        intro="Three plain words describe where a bullpen stands heading into the night."
      >
        <DefinitionGrid items={TEAM_STATES} />
      </Section>

      <Section
        id="arm-availability"
        title="Arm Availability"
        intro="For each reliever, BaseballOS shows one of four states based on recent workload and roster status."
      >
        <DefinitionGrid items={ARM_STATES} columns="sm:grid-cols-2 lg:grid-cols-4" />
      </Section>

      <Section
        id="bullpen-reads"
        title="Bullpen Reads"
        intro="These reads describe today's bullpen from different angles. Each is descriptive, not predictive."
      >
        <DefinitionGrid items={BULLPEN_READS} columns="sm:grid-cols-2 lg:grid-cols-3" />
      </Section>

      <Section id="freshness" title="Freshness Labels">
        <DefinitionGrid items={FRESHNESS_LABELS} columns="sm:grid-cols-2" />
      </Section>

      <Section id="using-reads" title="How to Use These Reads">
        <div className="space-y-4 text-sm leading-7 text-chalk400">
          {USING_READS.map(paragraph => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/methodology"
            className="inline-flex rounded border border-amber/35 px-3 py-2 font-mono text-xs uppercase tracking-widest text-amber transition-colors hover:bg-amber/10"
          >
            Read Methodology
          </Link>
          <Link
            to="/trust"
            className="inline-flex rounded border border-dirt px-3 py-2 font-mono text-xs uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/50 hover:text-amber"
          >
            View Data &amp; Trust
          </Link>
        </div>
      </Section>
    </div>
  )
}
