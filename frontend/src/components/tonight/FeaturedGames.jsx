import TonightGameCard from './TonightGameCard'
import { getVisibleFeaturedGames } from './tonightView'

export default function FeaturedGames({ payload }) {
  // Only non-final featured games; the section disappears when none remain.
  const games = getVisibleFeaturedGames(payload?.games, payload?.featured_game_pks)
  if (games.length === 0) return null
  return (
    <section className="mt-section min-w-0" aria-labelledby="tonight-featured-heading" data-testid="tonight-featured">
      <h2 id="tonight-featured-heading" className="font-mono text-xs uppercase tracking-widest text-chalk300">
        Games to Watch
      </h2>
      {/* A lone remaining card spans one comfortable column instead of leaving
          an empty half row; two or more keep the existing grid. */}
      <div
        className={`mt-3 grid min-w-0 grid-cols-1 gap-3 ${games.length > 1 ? 'desktop:grid-cols-2' : 'max-w-3xl'}`}
        data-featured-count={games.length}
      >
        {games.map(game => (
          <TonightGameCard key={game.game_pk} game={game} idPrefix="featured" />
        ))}
      </div>
    </section>
  )
}
