import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { ProductPageHeader, QuietState, displayDate } from './ProductPrimitives'

export default function ProductStories() {
  const request = useFetch(getBullpenDashboard)
  const feed = request.data?.stories || {}
  const items = Array.isArray(feed.items) ? feed.items : []
  const current = feed.freshness?.is_current === true && feed.freshness?.complete_enough_to_publish === true
  return (
    <div className="bos-page bos-page--reading py-8 md:py-10">
      <ProductPageHeader eyebrow="Stories" title="Stories" description={`${items.length} supported ${items.length === 1 ? 'storyline' : 'storylines'} in the served publication. A finite feed is not padded when no additional observation carries enough evidence.`} facts={[{ label: 'Data through', value: displayDate(feed.freshness?.data_through || feed.as_of_date) }]} />
      {!current && feed.freshness?.label && <div className="mt-7"><QuietState title="Published view">{feed.freshness.label}</QuietState></div>}
      <div className="divide-y divide-line">
        {items.map((story, index) => (
          <article key={story.story_id || index} className="py-9">
            <p className="bos-eyebrow text-brass">{String(story.story_type || 'Observation').replaceAll('_', ' ')}</p>
            <h2 className="mt-3 max-w-[30ch] font-display text-[1.8rem] font-semibold leading-tight text-chalk100">{story.headline}</h2>
            <p className="mt-4 max-w-measure whitespace-pre-line text-[0.9375rem] leading-7 text-chalk300">{story.share_summary || story.narrative}</p>
            {story.evidence?.length > 0 && <div className="mt-5 grid gap-3 md:grid-cols-2">{story.evidence.slice(0, 3).map((evidence, evidenceIndex) => <div key={evidence.key || evidenceIndex} className="grid grid-cols-[2rem_1fr] gap-3 border-t border-line pt-3"><span className="font-mono text-[10px] text-brass/70">E{evidenceIndex + 1}</span><p className="text-sm leading-6 text-chalk400">{evidence.text}</p></div>)}</div>}
            {story.team_id && <Link to={`/bullpen?view=board&team=${story.team_id}&source=stories`} className="bos-link mt-5">{story.team_name || 'Team'} board →</Link>}
          </article>
        ))}
      </div>
      {!request.loading && items.length === 0 && <QuietState title="Quiet">{feed.fallback || 'No supported storylines are publishable.'}</QuietState>}
    </div>
  )
}
