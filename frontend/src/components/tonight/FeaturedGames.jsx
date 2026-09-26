import TonightGameCard from './TonightGameCard'
import { featuredGames } from './tonightView'

export default function FeaturedGames({ payload }) {
  const games = featuredGames(payload)
  if (games.length === 0) return null
  return (
    <section className="mt-section min-w-0" aria-labelledby="tonight-featured-heading" data-testid="tonight-featured">
      <h2 id="tonight-featured-heading" className="font-mono text-xs uppercase tracking-widest text-chalk300">
        Games to Watch
      </h2>
      <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 desktop:grid-cols-2">
        {games.map(game => (
          <TonightGameCard key={game.game_pk} game={game} idPrefix="featured" />
        ))}
      </div>
    </section>
  )
}
