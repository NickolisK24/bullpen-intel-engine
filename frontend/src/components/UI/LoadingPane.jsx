// Animated skeleton loader with a pulsing baseball diamond glyph.
// Dark-themed to match the rest of the app (slate/zinc + amber).
export default function LoadingPane({ message = 'Loading...', label }) {
  // `label` kept as an alias so older call sites keep rendering correctly.
  const text = message ?? label ?? 'Loading...'

  return (
    <div className="flex flex-col items-center justify-center gap-5 py-20 text-chalk400">
      {/* Pulsing baseball diamond */}
      <div className="relative flex items-center justify-center w-20 h-20">
        <span
          className="absolute inset-0 rounded-md bg-amber/10 animate-ping"
          style={{ transform: 'rotate(45deg)' }}
        />
        <svg
          viewBox="0 0 100 100"
          className="relative w-16 h-16 text-amber animate-pulse"
          aria-hidden="true"
        >
          <g transform="rotate(45 50 50)">
            <rect
              x="18"
              y="18"
              width="64"
              height="64"
              rx="4"
              ry="4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinejoin="round"
              opacity="0.9"
            />
            {/* Bases */}
            <circle cx="18" cy="50" r="3.5" fill="currentColor" />
            <circle cx="50" cy="18" r="3.5" fill="currentColor" />
            <circle cx="82" cy="50" r="3.5" fill="currentColor" />
            <circle cx="50" cy="82" r="3.5" fill="currentColor" />
          </g>
          {/* Pitcher's mound */}
          <circle cx="50" cy="50" r="3" fill="currentColor" opacity="0.7" />
        </svg>
      </div>

      {/* Skeleton text + message */}
      <div className="flex flex-col items-center gap-2">
        <span className="font-mono text-xs tracking-widest uppercase text-chalk400">
          {text}
        </span>
        <div className="flex gap-1.5 mt-1">
          <span className="w-1.5 h-1.5 rounded-full bg-amber/60 animate-pulse" style={{ animationDelay: '0ms' }} />
          <span className="w-1.5 h-1.5 rounded-full bg-amber/60 animate-pulse" style={{ animationDelay: '150ms' }} />
          <span className="w-1.5 h-1.5 rounded-full bg-amber/60 animate-pulse" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  )
}
