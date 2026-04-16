// Red-tinted error card. Renders a Try Again button if an onRetry handler is provided.
export default function ErrorState({ message, onRetry }) {
  return (
    <div className="flex items-center justify-center py-10">
      <div className="w-full max-w-md rounded-lg border border-red-500/30 bg-red-500/5 p-6 text-center">
        <div className="flex justify-center mb-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-red-500/10 border border-red-500/30">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-5 h-5 text-red-400"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
        </div>

        <div className="font-mono text-xs uppercase tracking-widest text-red-400/80 mb-2">
          Something went wrong
        </div>

        <p className="text-chalk200 text-sm font-mono leading-relaxed mb-4 break-words">
          {message || 'An unexpected error occurred.'}
        </p>

        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-4 py-2 bg-red-500/10 border border-red-500/40 rounded text-red-300 text-xs font-mono uppercase tracking-widest hover:bg-red-500/20 hover:border-red-500/60 transition-colors"
          >
            Try Again
          </button>
        )}
      </div>
    </div>
  )
}
