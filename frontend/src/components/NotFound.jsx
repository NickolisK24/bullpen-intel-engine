import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <section className="mx-auto max-w-3xl px-5 py-16 sm:px-8" aria-labelledby="not-found-title">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-clay">BaseballOS</p>
      <h1 id="not-found-title" className="mt-3 font-display text-4xl text-chalk100 sm:text-5xl">
        Page not found
      </h1>
      <p className="mt-4 max-w-xl text-base leading-7 text-fog">
        This address does not match a current BaseballOS page.
      </p>
      <Link
        to="/"
        className="mt-7 inline-flex min-h-11 items-center border border-amber/50 px-4 py-2 text-sm font-semibold text-amber hover:border-amber focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-amber"
      >
        Return to BaseballOS
      </Link>
    </section>
  )
}
