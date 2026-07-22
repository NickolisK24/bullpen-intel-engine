import { Link } from 'react-router-dom'
import { PUBLIC_BOUNDARIES } from '../../utils/publicBoundaries'

// The Methodology page answers one question: "How does BaseballOS compute what
// it shows me?" It is a static explanation of the public read process — what
// evidence is examined, how an arm read and a team read are formed, how
// freshness governs publication, and what BaseballOS refuses to claim. It holds
// no live data: the receipts live on the Team Board and Reliever Finder, the
// vocabulary lives on How to Read, and current system status lives on Data &
// Trust. Those pages are linked, never duplicated here.
//
// The worked example is illustrative and fixed. Its inputs and public status are
// anchored to the canonical availability rule proven by
// backend/tests/test_availability.py::TestAvailabilityClassification
// ::test_monitor_for_light_yesterday_workload — a single 16-pitch appearance
// yesterday classifies as On Watch (STATUS_MONITOR). It is not live MLB data.

const ARM_STATUSES = [
  {
    label: 'Available',
    body: 'Recent workload leaves the arm in a clean spot for normal bullpen coverage.',
  },
  {
    label: 'On Watch',
    body: 'Recent work is worth a check before counting on a full late-inning lane.',
  },
  {
    label: 'Limited',
    body: 'Recent usage narrows how comfortably the arm can be used right now.',
  },
  {
    label: 'Unavailable',
    body: 'Recent workload, or roster context, keeps the arm out of today’s available group.',
  },
]

const TEAM_STATES = [
  {
    label: 'Fresh',
    body: 'The reliever group has room to maneuver in the latest completed-game data.',
  },
  {
    label: 'Stretched',
    body: 'Recent work has narrowed the clean late-inning options.',
  },
  {
    label: 'Vulnerable',
    body: 'The current shape of the group leaves little margin if the game turns.',
  },
]

const EXAMINED_INPUTS = [
  ['Recent appearances', 'When the arm last worked, and how often across the recent window.'],
  ['Pitch counts', 'How many pitches were thrown in each recent outing — the most direct workload signal.'],
  ['Recent innings and outs', 'A second volume check when pitch-count detail is incomplete or noisy.'],
  ['Days since the last appearance', 'The primary recovery signal; back-to-back use reads differently than several days of rest.'],
  ['Repeated or consecutive-day usage', 'Frequent short outings can narrow bullpen flexibility even when no single outing is heavy.'],
  ['Recent workload windows', 'Rolling recent-day windows so a build-up of work is visible, not just yesterday.'],
  ['Observed relief usage and eligibility', 'How the arm has actually been used, from public game logs and roster status.'],
  ['Current roster context', 'Whether the pitcher is on the active roster, per public roster data.'],
  ['Team availability distribution', 'How Available, On Watch, Limited, and Unavailable arms are spread across the group.'],
  ['Data-through date, freshness, and coverage', 'The completed-game date each read is based on, and whether the day’s data is complete enough to publish.'],
]

const LIMITATIONS = [
  PUBLIC_BOUNDARIES.noPredictions,
  PUBLIC_BOUNDARIES.noPicks,
  PUBLIC_BOUNDARIES.noBettingAdvice,
  PUBLIC_BOUNDARIES.noPrivateInjuryClaims,
  PUBLIC_BOUNDARIES.noManagerCertainty,
  'Workload status is not a diagnosis, and it is not a measure of how good a pitcher is.',
  'A team state describes a bullpen’s current shape. It is not a ranking, a grade, or a predicted game result.',
  'Public role reads reflect observed usage patterns and trusted public evidence, not a manager’s plan.',
  'Missing or stale evidence can reduce a read or withhold it entirely. Quiet or withheld output is intentional.',
]

const INSPECT_LINKS = [
  { to: '/bullpen', label: 'Team Bullpens — see each bullpen’s state and its receipts' },
  { to: '/bullpen?view=compare', label: 'Compare Bullpens — put two teams’ pens side by side' },
  { to: '/bullpen?view=pitchers', label: 'Reliever Finder — look up a reliever’s recent workload' },
  { to: '/how-to-read', label: 'How to Read — compact definitions of every public label' },
  { to: '/trust', label: 'Data & Trust — current freshness, coverage, and reliability' },
]

function SubHead({ eyebrow, children, id }) {
  return (
    <div className="mb-3">
      {eyebrow && (
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/75">
          {eyebrow}
        </div>
      )}
      <h2 id={id} className="mt-1 font-display text-2xl tracking-wide text-chalk100 scroll-mt-24">
        {children}
      </h2>
    </div>
  )
}

export default function Methodology() {
  return <MethodologyView />
}

export function MethodologyView() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-3xl mx-auto">
      <header className="mb-8 border-b border-dirt pb-4">
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/75">
          Methodology
        </div>
        <h1 className="mt-1 font-display text-3xl sm:text-4xl tracking-wide text-chalk100">
          How BaseballOS reads a bullpen
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-chalk300">
          BaseballOS describes the current state of every MLB bullpen from recent,
          completed-game data. It reads recent workload, rest, role and roster
          context, and freshness, and it shows why each read exists. When the
          evidence is missing or stale, it withholds the read instead of guessing.
        </p>
      </header>

      <div className="space-y-10">
        {/* A / B — what is examined (inbound anchor: #methodology, #data-sources) */}
        <section id="methodology" className="scroll-mt-24">
          <SubHead eyebrow="What it examines" id="data-sources">
            The evidence behind a read
          </SubHead>
          <p className="max-w-2xl text-sm leading-relaxed text-chalk300">
            Every read is built from public MLB data — rosters, game logs, and box
            scores from completed games. BaseballOS looks at a small set of
            trusted workload and context signals:
          </p>
          <dl className="mt-4 space-y-3">
            {EXAMINED_INPUTS.map(([term, detail]) => (
              <div key={term} className="rounded border border-dirt bg-chalk/10 p-3">
                <dt className="font-mono text-sm text-chalk100">{term}</dt>
                <dd className="mt-1 text-xs leading-relaxed text-chalk400">{detail}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-4 space-y-2 text-xs leading-relaxed text-chalk500">
            <p>
              Workload evidence describes how much an arm has worked recently. It
              is not a measure of pitcher quality or performance.
            </p>
            <p>
              Roster context describes whether a pitcher is available to the team
              on paper. {PUBLIC_BOUNDARIES.notHealthClaim}
            </p>
            <p>
              An appearance with an unknown pitch count stays partly unknown — a
              missing value is never treated as zero.
            </p>
          </div>
        </section>

        {/* C — how an arm read is formed */}
        <section className="scroll-mt-24">
          <SubHead eyebrow="One reliever">How an arm read is formed</SubHead>
          <p className="max-w-2xl text-sm leading-relaxed text-chalk300">
            The workload and context signals above resolve into one of four public
            availability states. The state reflects recent workload and trusted
            public context — not a headline number, and not a rank.
          </p>
          <dl className="mt-4 space-y-2">
            {ARM_STATUSES.map(status => (
              <div key={status.label} className="flex flex-col gap-1 rounded border border-dirt bg-chalk/10 p-3 sm:flex-row sm:gap-3">
                <dt className="shrink-0 font-mono text-sm text-chalk100 sm:w-28">{status.label}</dt>
                <dd className="text-xs leading-relaxed text-chalk400">{status.body}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 max-w-2xl text-xs leading-relaxed text-chalk500">
            Freshness, missing evidence, roster context, or incomplete coverage can
            limit a read or withhold it. An availability state is not a health
            clearance, is not a promise the pitcher can pitch, and does not say
            whether a manager will use him. For compact definitions of every
            label, see{' '}
            <Link to="/how-to-read" className="text-amber underline decoration-amber/40 underline-offset-2 hover:decoration-amber">
              How to Read
            </Link>.
          </p>
        </section>

        {/* D — how a team read is formed */}
        <section className="scroll-mt-24">
          <SubHead eyebrow="One bullpen">How a team read is formed</SubHead>
          <p className="max-w-2xl text-sm leading-relaxed text-chalk300">
            A bullpen-level read describes the current shape of the whole reliever
            group — supported by how its arms are spread across the four
            availability states and other public team context. It is a plain
            description of team state, for example:
          </p>
          <dl className="mt-4 space-y-2">
            {TEAM_STATES.map(state => (
              <div key={state.label} className="flex flex-col gap-1 rounded border border-dirt bg-chalk/10 p-3 sm:flex-row sm:gap-3">
                <dt className="shrink-0 font-mono text-sm text-chalk100 sm:w-28">{state.label}</dt>
                <dd className="text-xs leading-relaxed text-chalk400">{state.body}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 max-w-2xl text-xs leading-relaxed text-chalk500">
            Team state and individual arm status answer different questions, so
            BaseballOS keeps them separate. A team read is not a score, and more
            Available arms does not automatically make one bullpen &ldquo;better&rdquo; than
            another; it says nothing about who wins or which inning an arm will
            cover. The live receipts behind a team read live on the{' '}
            <Link to="/bullpen" className="text-amber underline decoration-amber/40 underline-offset-2 hover:decoration-amber">
              Team Board
            </Link>.
          </p>
        </section>

        {/* Worked example */}
        <section aria-labelledby="worked-example" className="scroll-mt-24">
          <SubHead eyebrow="Worked example" id="worked-example">
            From facts to a public read
          </SubHead>
          <div className="rounded-lg border border-amber/30 bg-amber/5 p-4">
            <p className="font-mono text-[11px] uppercase tracking-widest text-amber/80">
              Illustrative example — not current MLB data
            </p>
            <dl className="mt-3 space-y-3 text-sm leading-relaxed">
              <div>
                <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">State</dt>
                <dd className="mt-0.5 text-chalk100">Example Reliever &mdash; On Watch</dd>
              </div>
              <div>
                <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">Why</dt>
                <dd className="mt-0.5 text-chalk300">
                  A single light outing yesterday is worth a check before counting
                  on a full late-inning lane.
                </dd>
              </div>
              <div>
                <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">Evidence</dt>
                <dd className="mt-0.5 text-chalk300">
                  One appearance yesterday &middot; 16 pitches &middot; no other
                  outings in the recent window.
                </dd>
              </div>
              <div>
                <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">Freshness</dt>
                <dd className="mt-0.5 text-chalk300">
                  Data through the example&rsquo;s most recent completed game
                  (illustrative &mdash; not live tracking).
                </dd>
              </div>
              <div>
                <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">Limitations</dt>
                <dd className="mt-0.5 text-chalk300">
                  On Watch does not mean the pitcher is hurt or cleared, does not
                  predict whether he will appear, and is not a comment on how good
                  he is.
                </dd>
              </div>
            </dl>
          </div>
          <p className="mt-3 max-w-2xl text-xs leading-relaxed text-chalk500">
            Try the same read on real, current arms in the{' '}
            <Link to="/bullpen?view=pitchers" className="text-amber underline decoration-amber/40 underline-offset-2 hover:decoration-amber">
              Reliever Finder
            </Link>.
          </p>
        </section>

        {/* Freshness & publication gates */}
        <section className="scroll-mt-24">
          <SubHead eyebrow="Freshness & safeguards">When BaseballOS publishes — and when it doesn&rsquo;t</SubHead>
          <ul className="max-w-2xl space-y-2 text-sm leading-relaxed text-chalk300">
            <li className="flex gap-2"><span className="text-amber" aria-hidden="true">&bull;</span><span>Every read carries a data-through date — the completed-game date it is based on. When shown, an updated time and the data-through date answer different questions.</span></li>
            <li className="flex gap-2"><span className="text-amber" aria-hidden="true">&bull;</span><span>Stale data is labeled as stale; it never appears as current.</span></li>
            <li className="flex gap-2"><span className="text-amber" aria-hidden="true">&bull;</span><span>Partial or incomplete coverage is disclosed, and comparisons that would be unsafe are withheld.</span></li>
            <li className="flex gap-2"><span className="text-amber" aria-hidden="true">&bull;</span><span>Unknown inputs stay unknown. On a quiet or incomplete day, BaseballOS may publish no read at all.</span></li>
            <li className="flex gap-2"><span className="text-amber" aria-hidden="true">&bull;</span><span>A &ldquo;current&rdquo; label means the latest completed-game data — not real-time, in-game tracking. BaseballOS does not track live and does not predict whether a pitcher will appear.</span></li>
          </ul>
          <p className="mt-3 max-w-2xl text-xs leading-relaxed text-chalk500">
            For current system status, coverage, and validation, see{' '}
            <Link to="/trust" className="text-amber underline decoration-amber/40 underline-offset-2 hover:decoration-amber">
              Data & Trust
            </Link>.
          </p>
        </section>

        {/* Limitations & refusals (inbound anchor: #known-limitations) */}
        <section id="known-limitations" className="scroll-mt-24">
          <SubHead eyebrow="What it will not claim">Limitations and refusals</SubHead>
          <p className="max-w-2xl text-sm leading-relaxed text-chalk300">
            {PUBLIC_BOUNDARIES.descriptiveScope}
          </p>
          <ul className="mt-4 max-w-2xl space-y-2 text-sm leading-relaxed text-chalk400">
            {LIMITATIONS.map(item => (
              <li key={item} className="flex gap-2">
                <span className="text-amber" aria-hidden="true">&bull;</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* Inspect the work */}
        <section className="scroll-mt-24">
          <SubHead eyebrow="Inspect the work">See the reads on live bullpens</SubHead>
          <ul className="space-y-2">
            {INSPECT_LINKS.map(link => (
              <li key={link.to}>
                <Link
                  to={link.to}
                  className="inline-flex min-w-0 rounded border border-dirt bg-chalk/10 px-3 py-2 text-sm text-chalk200 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
