import { Link } from 'react-router-dom'

const HERO = {
  eyebrow: 'ABOUT',
  title: 'About BaseballOS',
  lead: 'BaseballOS exists to make bullpen context easier to understand.',
  sub: 'A public MLB bullpen intelligence platform that reads workload, availability, and late-inning context — and explains which bullpens are fresh, stretched, or vulnerable, and why.',
}

const WHY_BODY = [
  'Bullpen context is hard to see in one place. A box score tells you who pitched and for how long — but not how workload, rest, availability, and late-inning flexibility actually fit together heading into tonight.',
  "That picture usually lives in scattered notes, usage charts, and gut feel. BaseballOS pulls it into one clear, current read: how much each bullpen is carrying, who's rested, and where the late-inning margin is thin — described in plain baseball language, with the evidence shown alongside it.",
]

const PRODUCT_CARDS = [
  {
    title: 'Reads Workload',
    body: 'Tracks recent usage and rest across every MLB bullpen, so you can see how much each bullpen is carrying today.',
  },
  {
    title: 'Explains Availability',
    body: 'Turns that workload into a clear read on which arms are available, on watch, limited, or unavailable — and why.',
  },
  {
    title: 'Explains the Game',
    body: 'Highlights the bullpen storylines worth watching each day, from stretched bullpens to teams entering the night with room to maneuver.',
  },
]

const DOES_NOT_DO = [
  'No picks. It never tells you who to use or who to bet.',
  "No predictions. It describes today's context, not tomorrow's outcome.",
  'No betting advice. It is not a wagering or odds product.',
  'No private injury claims. The absence of a public flag is not a health claim.',
  'No certainty about manager decisions. It cannot see bullpen phones, intent, or final game-day calls.',
]

const TRUST_BODY = [
  "BaseballOS is built to be checkable. Every read shows how current it is — the date the data runs through and when it was last updated — so you always know what you're looking at. The reasoning behind each read is documented, and the limits are stated plainly rather than hidden.",
  "If a read can't be made with confidence, BaseballOS says so instead of guessing.",
]

function Section({ title, children, className = '' }) {
  return (
    <section className={`card p-5 sm:p-6 ${className}`}>
      <h2 className="font-display text-2xl tracking-wider text-chalk100">
        {title}
      </h2>
      <div className="mt-4">
        {children}
      </div>
    </section>
  )
}

export default function About() {
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

      <Section title="Why BaseballOS exists">
        <div className="space-y-4 text-sm leading-7 text-chalk400">
          {WHY_BODY.map(paragraph => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
      </Section>

      <Section title="What BaseballOS does">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {PRODUCT_CARDS.map(card => (
            <article key={card.title} className="rounded border border-dirt bg-field/45 p-4">
              <h3 className="font-mono text-xs uppercase tracking-widest text-amber/80">
                {card.title}
              </h3>
              <p className="mt-3 text-sm leading-6 text-chalk400">
                {card.body}
              </p>
            </article>
          ))}
        </div>
      </Section>

      <Section title="What BaseballOS does not do">
        <p className="max-w-3xl text-sm leading-7 text-chalk400">
          BaseballOS is descriptive by design. It stays in its lane on purpose.
        </p>
        <ul className="mt-5 space-y-3">
          {DOES_NOT_DO.map(item => (
            <li key={item} className="flex gap-3 text-sm leading-6 text-chalk400">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-chalk600" aria-hidden="true" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Why you can trust it">
        <div className="space-y-4 text-sm leading-7 text-chalk400">
          {TRUST_BODY.map(paragraph => (
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

      <section className="rounded border border-dirt bg-field/50 p-5">
        <p className="font-mono text-sm uppercase tracking-widest text-chalk200">
          Making bullpen context easier to understand.
        </p>
      </section>
    </div>
  )
}
