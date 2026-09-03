import { Link } from 'react-router-dom'
import {
  ARM_AVAILABILITY_DEFINITIONS,
  AVAILABILITY_SCOPE_DESCRIPTION,
  CONCEPT_DEFINITIONS,
  CURRENT_READ_AVAILABILITY_RELATIONSHIP,
  DATA_STATUS_DEFINITIONS,
  FRESHNESS_LABEL_DEFINITIONS,
  LIMITED_FAMILY_BOUNDARY,
  LIMITED_FAMILY_DISAMBIGUATION,
  PITCHER_CURRENT_READ_DEFINITIONS,
  PITCHER_ROLE_DEFINITIONS,
  PROVENANCE_LABEL_DEFINITIONS,
  WORKLOAD_DATA_DEFINITIONS,
  WORKLOAD_DATA_FAMILY,
  READ_CONFIDENCE_BOUNDARY,
  READ_CONFIDENCE_DEFINITIONS,
  RESTED_AVAILABILITY_DISTINCTION,
  SUPPORTING_CONCEPT_DEFINITIONS,
  SUPPORTING_READ_BOUNDARY,
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

const PITCHER_ROLES = PITCHER_ROLE_DEFINITIONS.map(asCard)

const PITCHER_READS = PITCHER_CURRENT_READ_DEFINITIONS.map(asCard)

const READ_CONFIDENCE = READ_CONFIDENCE_DEFINITIONS.map(asCard)

// Every supporting family, each rendered with its concept name attached.
const SUPPORTING_READS = [
  SUPPORTING_CONCEPT_DEFINITIONS.lateInningAvailability,
  SUPPORTING_CONCEPT_DEFINITIONS.restedOptions,
  SUPPORTING_CONCEPT_DEFINITIONS.lateInningPressure,
  CONCEPT_DEFINITIONS.concentration,
  SUPPORTING_CONCEPT_DEFINITIONS.coverageSafety,
  SUPPORTING_CONCEPT_DEFINITIONS.depthSafety,
  SUPPORTING_CONCEPT_DEFINITIONS.trustedArms,
].map(asCard)

// The four labels that share the word 'Limited', each tagged with the family
// it belongs to so the difference is stated rather than inferred.
const LIMITED_FAMILY = LIMITED_FAMILY_DISAMBIGUATION.map(entry => ({
  term: `${entry.name} — ${entry.family}`,
  detail: entry.definition,
}))

const FRESHNESS_LABELS = FRESHNESS_LABEL_DEFINITIONS.map(asCard)

const DATA_STATUSES = DATA_STATUS_DEFINITIONS.map(asCard)

const PROVENANCE_LABELS = PROVENANCE_LABEL_DEFINITIONS.map(asCard)
const WORKLOAD_DATA = WORKLOAD_DATA_DEFINITIONS.map(asCard)

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
          <h3 className="font-mono text-xs uppercase tracking-widest text-metadata-accent">
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
        <div className="font-mono text-xs uppercase tracking-widest text-metadata-accent">
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
        intro={AVAILABILITY_SCOPE_DESCRIPTION}
      >
        <DefinitionGrid items={ARM_STATES} columns="sm:grid-cols-2 lg:grid-cols-4" />
      </Section>

      <Section
        id="pitcher-role"
        title="Pitcher Role"
        intro="Role describes how a pitcher has been used. It does not describe whether he is available tonight, and it is not a quality grade."
      >
        <DefinitionGrid items={PITCHER_ROLES} columns="sm:grid-cols-2 lg:grid-cols-3" />
      </Section>

      <Section
        id="pitcher-current-read"
        title="Pitcher Current Read"
        intro={`${CURRENT_READ_AVAILABILITY_RELATIONSHIP} It is a different question from role.`}
      >
        <DefinitionGrid items={PITCHER_READS} columns="sm:grid-cols-2 lg:grid-cols-3" />
        <div className="mt-8 rounded-lg border border-amber/25 bg-amber/5 p-5">
          <h3 className="font-mono text-xs uppercase tracking-widest text-metadata-accent">
            Four labels share the word &ldquo;Limited&rdquo;
          </h3>
          <dl className="mt-4 space-y-3">
            {LIMITED_FAMILY.map(item => (
              <div key={item.term}>
                <dt className="text-sm font-semibold text-chalk100">{item.term}</dt>
                <dd className="text-sm leading-6 text-chalk400">{item.detail}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-sm leading-6 text-chalk400">{LIMITED_FAMILY_BOUNDARY}</p>
        </div>
      </Section>

      <Section
        id="read-confidence"
        title="Read Confidence"
        intro={READ_CONFIDENCE_BOUNDARY}
      >
        <DefinitionGrid items={READ_CONFIDENCE} columns="sm:grid-cols-2 lg:grid-cols-4" />
      </Section>

      <Section
        id="supporting-reads"
        title="Bullpen Supporting Reads"
        intro={SUPPORTING_READ_BOUNDARY}
      >
        <p className="mb-5 max-w-3xl text-sm leading-7 text-chalk400">
          {RESTED_AVAILABILITY_DISTINCTION}
        </p>
        <DefinitionGrid items={SUPPORTING_READS} columns="sm:grid-cols-2 lg:grid-cols-3" />
      </Section>

      <Section
        id="freshness"
        title="Freshness & Data Status"
        intro="Three different clocks, and a status describing the data itself rather than any bullpen."
      >
        <DefinitionGrid items={FRESHNESS_LABELS} columns="sm:grid-cols-2 lg:grid-cols-3" />
        <h3 className="mt-8 font-mono text-xs uppercase tracking-widest text-metadata-accent">
          Data status
        </h3>
        <div className="mt-4">
          <DefinitionGrid items={DATA_STATUSES} columns="sm:grid-cols-2 lg:grid-cols-4" />
        </div>
        <h3 className="mt-8 font-mono text-xs uppercase tracking-widest text-metadata-accent">
          {WORKLOAD_DATA_FAMILY}
        </h3>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-chalk400">
          Data status describes the published read. Workload Data describes one
          pitcher&rsquo;s stored workload record, which is a different question.
        </p>
        <div className="mt-4">
          <DefinitionGrid items={WORKLOAD_DATA} columns="sm:grid-cols-2 lg:grid-cols-4" />
        </div>
        <h3 className="mt-8 font-mono text-xs uppercase tracking-widest text-metadata-accent">
          Provenance stamps
        </h3>
        <div className="mt-4">
          <DefinitionGrid items={PROVENANCE_LABELS} columns="sm:grid-cols-2" />
        </div>
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
