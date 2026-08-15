import { useFetch } from '../../hooks/useFetch'
import { getTeams, getTonightIntelligence } from '../../utils/api'
import { getTonightCards } from '../home/IntelligenceSurface'
import { ProductPageHeader, QuietState, displayDate } from './ProductPrimitives'
import { Link } from 'react-router-dom'

export default function Slate() {
  const teams = useFetch(getTeams)
  const request = useFetch(getTonightIntelligence)
  const cards = getTonightCards(request.data, teams.data || [], 30)
  const referenceDate = request.data?.reference_date
  return (
    <div className="bos-page py-8 md:py-10">
      <ProductPageHeader
        eyebrow="Today · The Slate"
        title="What tonight asks of these bullpens"
        description="Each bullpen brings an observable condition into tonight's game. BaseballOS does not say which bullpen has the advantage."
        facts={[
          { label: 'Baseball date', value: displayDate(referenceDate) },
          { label: 'Noted conditions', value: request.data ? String(request.data.card_count || 0) : null },
        ]}
      />
      {cards.length > 0 ? (
        <div className="grid gap-6 py-9 lg:grid-cols-2">
          {cards.map(card => (
            <article key={card.key} className="border border-line bg-panel p-6">
              <p className="bos-eyebrow text-brass">{card.label}</p>
              <h2 className="mt-3 font-display text-2xl font-semibold text-chalk100">{card.headline}</h2>
              <p className="mt-4 text-[0.9375rem] leading-6 text-chalk300">{card.summary}</p>
              {card.teamContext && <p className="mt-3 text-sm leading-6 text-chalk500">{card.teamContext}</p>}
              {card.evidence?.length > 0 && <p className="mt-5 border-t border-line pt-4 font-mono text-[11px] leading-5 text-chalk500">{card.evidence.join(' · ')}</p>}
              {card.href && <Link to={card.href} className="bos-link mt-4">View team evidence →</Link>}
            </article>
          ))}
        </div>
      ) : (
        <div className="py-9"><QuietState title="Slate">{request.data?.empty_reason === 'no_teams_playing_today' ? 'No MLB games are scheduled for this baseball date.' : 'No supported bullpen condition is publishable for this slate yet.'}</QuietState></div>
      )}
    </div>
  )
}
