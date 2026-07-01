import { Link } from 'react-router-dom'
import { CONCEPT_DEFINITIONS } from '../../utils/bullpenConcepts'

const HERO = {
  eyebrow: 'HOW TO READ',
  title: 'How to Read BaseballOS',
  lead: 'BaseballOS uses plain baseball reads to explain bullpen state.',
  sub: "Every label on the site describes today's context — how much a bullpen is carrying, who's rested, and where the late-inning margin is thin. Here's what each term means, in one line.",
}

const TEAM_STATES = [
  {
    title: 'Fresh',
    body: 'The bullpen comes in mostly rested, with room to maneuver late.',
  },
  {
    title: 'Stretched',
    body: 'The bullpen is thin on rested arms after recent work.',
  },
  {
    title: 'Vulnerable',
    body: 'Little late-inning margin remains if the game runs long.',
  },
]

const ARM_STATES = [
  {
    title: 'Available',
    body: 'Rested enough to pitch today.',
  },
  {
    title: 'On Watch',
    body: 'Usable, but recent work is worth watching.',
  },
  {
    title: 'Limited',
    body: 'Available only in a reduced role after recent work.',
  },
  {
    title: 'Unavailable',
    body: 'Not available today because of rest or roster status.',
  },
]

// TODO: Move Coverage Safety and Trusted Arms into bullpenConcepts.js when they become shared public concepts.
const BULLPEN_READS = [
  {
    title: CONCEPT_DEFINITIONS.pressure.name,
    body: 'How much workload strain the bullpen is carrying today.',
  },
  {
    title: CONCEPT_DEFINITIONS.recovery.name,
    body: CONCEPT_DEFINITIONS.recovery.definition,
  },
  {
    title: CONCEPT_DEFINITIONS.concentration.name,
    body: 'Whether recent work is spread around or clustered on a few arms.',
  },
  {
    title: CONCEPT_DEFINITIONS.cleanOptions.name,
    body: CONCEPT_DEFINITIONS.cleanOptions.definition,
  },
  {
    title: 'Coverage Safety',
    body: 'Whether the bullpen can cover the late innings if the game runs long.',
  },
  {
    title: 'Trusted Arms',
    body: 'The rested, unrestricted arms a manager can lean on late.',
  },
]

const FRESHNESS_LABELS = [
  {
    title: 'Data through',
    body: 'The latest completed MLB date included in the read.',
  },
  {
    title: 'Updated',
    body: 'When BaseballOS last wrote new baseball data.',
  },
]

const USING_READS = [
  'BaseballOS describes bullpen context. It does not predict outcomes, rank pitchers, or tell you who to use.',
  'It shows how current the data is, explains how each read is built, and clearly states what it cannot see, including manager intent, bullpen phones, and final game-day decisions.',
  "When a read cannot be made with confidence, BaseballOS says so instead of guessing.",
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
