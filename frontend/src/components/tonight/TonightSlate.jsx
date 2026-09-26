import TonightGameCard from './TonightGameCard'

export default function TonightSlate({ games }) {
  const list = Array.isArray(games) ? games : []
  if (list.length === 0) return null
  return (
    <section className="mt-section min-w-0" aria-labelledby="tonight-slate-heading" data-testid="tonight-slate">
      <h2 id="tonight-slate-heading" className="font-mono text-xs uppercase tracking-widest text-chalk300">
        Tonight&apos;s Slate
      </h2>
      <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 desktop:grid-cols-2">
        {list.map(game => (
          <TonightGameCard key={game.game_pk} game={game} idPrefix="slate" />
        ))}
      </div>
    </section>
  )
}
